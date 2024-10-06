import copy
import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from instruction_handlers import InstructionHandlers
from utils import interpolate_variables, parse_plan, load_state, save_state
from llm_interface import LLMInterface
from config import LLM_MODEL, GIT_REPO_PATH, VM_SPEC_PATH
from git_manager import GitManager
import git  # Make sure this import is at the top of the file

def show_file(repo, commit_hash, file_path):
    try:
        return repo.git.show(f'{commit_hash}:{file_path}')
    except git.exc.GitCommandError as e:
        logging.error(f"Error showing file {file_path} at commit {commit_hash}: {str(e)}")
        raise

class PlanExecutionVM:
    def __init__(self, repo_path=None):
        self.state: Dict[str, Any] = {
            'variables': {},
            'errors': [],
            'previous_plans': [],
            'goal': None,
            'current_plan': [],
            'program_counter': 0,
            'goal_completed': False,
            'msgs': []
        }

        # Initialize logger
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.INFO)
        handler = logging.StreamHandler()
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s')
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)

        self.llm_interface = LLMInterface(LLM_MODEL)
        
        # Use the provided repo_path or the default GIT_REPO_PATH
        self.repo_path = repo_path or GIT_REPO_PATH
        self.git_manager = GitManager(self.repo_path)

        # Change the current working directory to the Git repo path
        os.chdir(self.repo_path)

        self.handlers_registered = False
        self.register_handlers()

        self.load_state = self.load_state  # This line ensures the method is available

    def register_handlers(self):
        if not self.handlers_registered:
            self.instruction_handlers = InstructionHandlers(self)
            self.register_instruction('retrieve_knowledge_graph', self.instruction_handlers.retrieve_knowledge_graph_handler)
            self.register_instruction('retrieve_knowledge_embedded_chunks', self.instruction_handlers.retrieve_knowledge_embedded_chunks_handler)
            self.register_instruction('llm_generate', self.instruction_handlers.llm_generate_handler)
            self.register_instruction('condition', self.instruction_handlers.condition_handler)
            self.register_instruction('assign', self.instruction_handlers.assign_handler)
            self.register_instruction('reasoning', self.instruction_handlers.reasoning_handler)
            self.handlers_registered = True

    def register_instruction(self, instruction_name: str, handler_method):
        """
        Registers an instruction handler.
        """
        if not isinstance(instruction_name, str) or not callable(handler_method):
            self.logger.error("Invalid instruction registration.")
            self.state['errors'].append("Invalid instruction registration.")
            return
        setattr(self.instruction_handlers, f"{instruction_name}_handler", handler_method)
        self.logger.info(f"Registered handler for instruction: {instruction_name}")

    def set_goal(self, goal: str) -> None:
        if not isinstance(goal, str):
            self.logger.error("Goal must be a string.")
            self.state['errors'].append("Goal must be a string.")
            return
        self.state['goal'] = goal
        self.logger.info(f"Goal set: {goal}")
        save_state(self.state, self.repo_path)

    def resolve_parameter(self, param):
        if isinstance(param, dict) and 'var' in param:
            var_name = param['var']
            value = self.state['variables'].get(var_name)
            self.logger.info(f"Resolved variable '{var_name}' to value: {value}")
            return value
        elif isinstance(param, str):
            return interpolate_variables(param, self.state['variables'])
        else:
            return param

    def _commit(self, action: str, detail: str = "") -> None:
        """
        Helper method to create and commit meaningful commit messages.
        
        Parameters:
            action (str): A brief description of the action performed.
            detail (str): Additional details about the action.
        """
        if detail:
            commit_message = f"{action}: {detail}"
        else:
            commit_message = action
        self.git_manager.commit_changes(commit_message)

    def execute_step_handler(self, step: Dict[str, Any]) -> bool:
        step_type = step.get('type')
        params = step.get('parameters', {})
        seq_no = step.get('seq_no', 'Unknown')  # Get seq_no, default to 'Unknown' if not present
        if not isinstance(step_type, str):
            self.logger.error("Invalid step type.")
            self.state['errors'].append("Invalid step type.")
            return False
        handler = getattr(self.instruction_handlers, f"{step_type}_handler", None)
        if handler:
            success = handler(params)
            if success:
                save_state(self.state, self.repo_path)  # Save state after successful step execution
                self.logger.info(f"Saved VM state after executing step {self.state['program_counter']}")
            
            # Log the updated variables
            self.logger.debug(f"Current Variables: {json.dumps(self.state['variables'], indent=2)}")
            
            # Prepare commit message
            commit_message = f"[seq_no: {seq_no}][{step_type}] - Executed step\n\n"
            commit_message += "Input Parameters:\n"
            for k, v in params.items():
                value_preview = str(v)[:50] + '...' if len(str(v)) > 50 else str(v)
                commit_message += f"- {k}: {value_preview}\n"
            
            commit_message += "\nOutput Variables:\n"
            output_vars = params.get('output_var')
            if isinstance(output_vars, str):
                output_vars = [output_vars]
            elif not isinstance(output_vars, list):
                output_vars = []
            for k in output_vars:
                v = self.state['variables'].get(k)
                value_preview = str(v)[:50] + '...' if len(str(v)) > 50 else str(v)
                commit_message += f"- {k}: {value_preview}\n"
            
            # Use the prepared commit_message
            self._commit("Execute Step", commit_message)
            
            return success
        else:
            self.logger.warning(f"Unknown instruction: {step_type}")
            return False

    def execute_plan(self, plan: List[Dict[str, Any]]) -> bool:
        self.logger.info("Starting plan execution.")
        while self.state['program_counter'] < len(plan):
            step = plan[self.state['program_counter']]
            success = self.execute_step_handler(step)
            if not success:
                self.logger.error(f"Execution failed at step {self.state['program_counter']}.")
                self.state['errors'].append(f"Execution failed at step {self.state['program_counter']}.")
                return False
            if self.state['goal_completed']:
                self.logger.info("Goal completed during plan execution.")
                return True
            self.state['program_counter'] += 1  # Increment program_counter after each step
        self.logger.info("Plan executed successfully.")
        return True

    def execute_subplan(self, subplan: List[Dict[str, Any]]) -> bool:
        self.logger.info("Executing subplan.")
        for step in subplan:
            success = self.execute_step_handler(step)
            if not success:
                self.logger.error("Subplan execution failed.")
                self.state['errors'].append("Subplan execution failed.")
                
                # Commit subplan failure to Git
                commit_message = f"Subplan execution failed at step: {step.get('type')}"
                if not self.git_manager.commit_changes(commit_message):
                    self.logger.error("Failed to commit changes to Git.")
                    # Handle the failure as needed
                
                return False
            if self.state['goal_completed']:
                break
        return True

    def generate_plan(self) -> bool:
        if not self.state['goal']:
            self.logger.error("No goal is set.")
            self.state['errors'].append("No goal is set.")
            return False

        self.logger.info("Generating plan using LLM.")
        prompt = f"""You are an intelligent assistant designed to analyze user queries and retrieve information from a knowledge graph multiple times. For the following goal, please:

1. Analyze the requester's intent and the requester's query:
   - Analyze and list the prerequisites of the query.
   - Analyze and list the assumptions of the query. 
   
2. Break Down query into sub-queries:
   - Each sub-query must be smaller, specific, retrievable with existing tools, and no further reasoning is required to achieve it.
   - Identify dependencies between sub-queries and draw a dependency graph.

3. Generate an Action Plan:
   - For each sub-query (Assumptions included), create a corresponding action step to achieve it.
   - Ensure the plan follows the format specified in the spec.md file.
   - Include a 'reasoning' step at the beginning of the plan that explains the overall approach and provides a dependency analysis of the steps.

Goal: {self.state['goal']}

Please provide your response as a JSON array of instruction steps, where each step has a 'type' and 'parameters'. 
The final step should assign the result to the 'result' variable. The 'reasoning' step should include both 'explanation' and 'dependency_analysis' parameters.

"""
        with open(VM_SPEC_PATH, 'r') as file:
            prompt += "the content of spec.md is:\n\n" + file.read()

        plan_response = self.llm_interface.generate(prompt)
        
        if not plan_response:
            self.logger.error("LLM failed to generate a response.")
            self.state['errors'].append("LLM failed to generate a response.")
            return False
        
        plan = parse_plan(plan_response)
        
        if plan:
            # Create a new branch for the plan
            branch_name = f"plan_{len(self.state['previous_plans'])}"
            try:
                if not self.git_manager.create_branch(branch_name):
                    self.logger.error(f"Failed to create branch '{branch_name}'.")
                    return False

                if not self.git_manager.checkout_branch(branch_name):
                    self.logger.error(f"Failed to checkout branch '{branch_name}'.")
                    return False
            except Exception as e:
                self.logger.error(f"Error in Git operations: {str(e)}")
                return False

            # Save the plan in the state and commit
            self.state['current_plan'] = plan
            self.state['previous_plans'].append(plan)
            self.logger.info("Plan generated and parsed successfully.")

            # Save state and commit the generated plan to Git
            save_state(self.state, self.repo_path)
            self._commit("Generate Plan", f"Generated new plan on branch '{branch_name}'")
            return True
        else:
            self.logger.error("Failed to parse the generated plan.")
            self.state['errors'].append("Failed to parse the generated plan.")
            return False

    def adjust_plan(self) -> bool:
        self.logger.info("Adjusting plan based on errors and context.")
        context_info = {
            'errors': self.state['errors'],
            'previous_plans': len(self.state['previous_plans'])
        }
        prompt = f"""You are an intelligent assistant designed to analyze and adjust plans. Given the following context and the original goal, please generate an adjusted plan:

1. Original Goal: {self.state['goal']}
2. Context Information:
   {json.dumps(context_info, indent=2)}

3. Current Plan:
   {json.dumps(self.state['current_plan'], indent=2)}

Please provide an adjusted plan that addresses the errors and follows the format specified in the spec.md file. The plan should be a JSON array of instruction steps, where each step has a 'type' and 'parameters'. The final step should assign the result to the 'result' variable.

Include a 'reasoning' step at the beginning of the plan that explains the adjustments made and provides a dependency analysis of the steps.

Ensure that the plan adheres to the following guidelines from spec.md:
1. Use supported instruction types: assign, llm_generate, retrieve_knowledge_graph, retrieve_knowledge_embedded_chunks, condition, and reasoning.
2. Follow the correct parameter structure for each instruction type.
3. Use variable references where appropriate, using the format {{"var": "variable_name"}}.
4. Include error handling and conditional logic where necessary.
5. Maintain a logical flow and dependencies between steps.

Provide your response as a valid JSON array of instruction steps.
"""

        with open(VM_SPEC_PATH, 'r') as file:
            prompt += "\n\nFor reference, here is the content of spec.md:\n\n" + file.read()

        plan_response = self.llm_interface.generate(prompt)
        if not plan_response:
            self.logger.error("LLM failed to generate an adjusted plan.")
            self.state['errors'].append("LLM failed to generate an adjusted plan.")
            return False

        new_plan = parse_plan(plan_response)
        if new_plan:
            # Create a new branch for the adjusted plan
            branch_name = f"adjusted_plan_{len(self.state['previous_plans'])}"
            if not self.git_manager.create_branch(branch_name):
                self.logger.error(f"Failed to create branch '{branch_name}'.")
                return False

            if not self.git_manager.checkout_branch(branch_name):
                self.logger.error(f"Failed to checkout branch '{branch_name}'.")
                return False

            # Save the adjusted plan in the state and commit
            self.state['current_plan'] = new_plan
            self.state['previous_plans'].append(new_plan)
            self.state['errors'] = []
            self.logger.info("Plan adjusted successfully.")

            # Save state and commit the adjusted plan to Git
            save_state(self.state, self.repo_path)
            self._commit("Adjust Plan", f"Adjusted plan on branch '{branch_name}'")
            return True
        else:
            self.logger.error("Failed to parse the adjusted plan.")
            self.state['errors'].append("Failed to parse the adjusted plan.")
            return False

    def update_plan(self, new_plan: List[Dict[str, Any]]) -> None:
        """
        Updates the current plan with a new plan.
        """
        if new_plan:
            self.state['current_plan'] = new_plan
            self.state['previous_plans'].append(new_plan)
            self.logger.info("Plan updated successfully.")
            
            # Commit the updated plan to Git
            commit_message = f"Updated plan:\n{json.dumps(new_plan, indent=2)}"
            if not self.git_manager.commit_changes(commit_message):
                self.logger.error("Failed to commit changes to Git.")
                # Handle the failure as needed
        else:
            self.logger.info("No changes to the current plan.")

    def run(self) -> None:
        max_iterations = 1
        iterations = 0

        while not self.state['goal_completed'] and iterations < max_iterations:
            self.logger.info(f">>>>>>>>>>>>>>>>>>>>Iteration {iterations}>>>>>>>>>>>>>>>>>>>")

            # Save iteration start to state and commit the start of a new iteration
            save_state(self.state, self.repo_path)
            self._commit("Start Iteration", f"Iteration {iterations} started.")
            iterations += 1

            if not self.state['goal']:
                self.logger.error("No goal is set.")
                self.state['errors'].append("No goal is set.")
                
                commit_message = "Error: No goal is set."
                if not self.git_manager.commit_changes(commit_message):
                    self.logger.error("Failed to commit changes to Git.")
                    # Handle the failure as needed
                
                break

            execution_success = self.execute_plan(self.state['current_plan'])
            if not execution_success:
                self.logger.error("Execution failed. Adjusting plan based on errors.")
                self.state['errors'].append("Execution failed. Adjusting plan based on errors.")
                
                # Commit the execution failure before adjustment
                self._commit("Execution Failed", "Initiating plan adjustment due to execution failure.")
                
                adjust_success = self.adjust_plan()
                if not adjust_success:
                    self.logger.error("Failed to adjust the plan. Stopping execution.")
                    self.state['errors'].append("Failed to adjust the plan. Stopping execution.")
                    
                    # Commit the adjustment failure to Git
                    self._commit("Plan Adjustment Failed", "Stopping execution due to failed plan adjustment.")
                    
                    break
                
            if self.state['goal_completed']:
                self.logger.info("Goal achieved successfully.")
                
                # Commit goal achievement to Git
                save_state(self.state, self.repo_path)
                self._commit("Goal Achieved", "Goal achieved successfully.")
                break

            self.evolve()

        if iterations >= max_iterations:
            self.logger.error("Maximum iterations reached without achieving the goal.")
            self.state['errors'].append("Maximum iterations reached without achieving the goal.")
            
            # Commit the iteration limit reached to Git
            commit_message = "Maximum iterations reached without achieving the goal."
            if not self.git_manager.commit_changes(commit_message):
                self.logger.error("Failed to commit changes to Git.")
                # Handle the failure as needed

        result = self.state['variables'].get('result')
        if result:
            result = interpolate_variables(result, self.state['variables'])
            print(f"\nFinal Result: {result}")
        else:
            print("\nNo result was generated.")

    def get_current_state(self) -> Dict[str, Any]:
        """
        Returns the current state of the VM.
        """
        return self.state


    def analyze_branches(self) -> None:
        """
        Analyze branches to inform future plan generation and adjustments.
        """
        branches = self.git_manager.list_branches()
        self.logger.info("Analyzing branches:")
        for branch in branches:
            self.logger.info(f"- {branch}")
            # Here you can implement logic to analyze each branch,
            # e.g., checking for successful goal completion,
            # the number of errors, etc.

    def evolve(self) -> None:
        """
        Evolve the VM's strategy based on branch analysis.
        """
        self.analyze_branches()
        # Implement logic to decide which branches to merge,
        # which plans to adjust, or whether to generate new plans
        # e.g., merge branches that led to successful goal completion

    def step(self):
        if self.state['program_counter'] < len(self.state['current_plan']):
            step = self.state['current_plan'][self.state['program_counter']]
            self.logger.info(f"Executing step {self.state['program_counter']}: {step['type']}")
            try:
                success = self.execute_step_handler(step)
                if not success:
                    self.logger.error(f"Failed to execute step {self.state['program_counter']}: {step['type']}")
                    return False
            except Exception as e:
                self.logger.error(f"Error executing step {self.state['program_counter']}: {str(e)}")
                self.state['errors'].append(f"Error in step {self.state['program_counter']}: {str(e)}")
                return False
            self.state['program_counter'] += 1
            save_state(self.state, self.repo_path)  # Save state after each step
            return True
        else:
            self.logger.info("Program execution complete.")
            return False

    def set_variable(self, var_name: str, value: Any) -> None:
        """
        Centralized method to set a variable in the VM's state.
        Logs the assignment and handles goal completion if needed.
        """
        self.state['variables'][var_name] = value
        self.logger.info(f"Variable '{var_name}' set to '{value}'.")
        
        # Mark goal as completed if 'result' is assigned
        if var_name == 'result':
            self.state['goal_completed'] = True
            self.logger.info("Goal has been marked as completed.")

    def get_variable(self, var_name: str) -> Any:
        """
        Centralized method to retrieve a variable's value from the VM's state.
        """
        return self.state['variables'].get(var_name)

    def load_state(self, commit_hash):
        """
        Load the state from a file based on the specific commit point.
        """
        loaded_state = load_state(commit_hash, self.repo_path)
        if loaded_state:
            self.state = loaded_state
            self.logger.info(f"State loaded from commit {commit_hash}")
        else:
            self.logger.error(f"Failed to load state from commit {commit_hash}")

if __name__ == "__main__":
    repo_path = GIT_REPO_PATH + datetime.now().strftime("%Y%m%d%H%M%S")
    vm = PlanExecutionVM(repo_path)
    vm.set_goal("summary the performance improvement of tidb from version 6.5 to newest version")
    
    if vm.generate_plan():
        print("Generated Plan:")
        print(json.dumps(vm.state['current_plan'], indent=2))
        vm.run()
    else:
        print("Failed to generate plan.")