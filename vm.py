import copy
import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from instruction_handlers import InstructionHandlers
from utils import interpolate_variables, parse_plan
from llm_interface import LLMInterface
from config import LLM_MODEL, GIT_REPO_PATH  # Update import
from milestones import Milestone  # Ensure this import is added
from git_manager import GitManager  # Add this import

class PlanExecutionVM:
    def __init__(self):
        self.variables: Dict[str, Any] = {}
        self.state: Dict[str, Any] = {
            'milestones': {},  # Change to store Milestone objects
            'errors': [],
            'previous_plans': [],
            'goal': None,
            'current_plan': [],
            'program_counter': 0,
            'goal_completed': False
        }

        # Initialize logger
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.INFO)
        handler = logging.StreamHandler()
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s')  # Updated formatter to include filename and line number
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)

        self.instruction_handlers = InstructionHandlers(self)
        self.llm_interface = LLMInterface(LLM_MODEL)
        #add a time stamp to the git repo path
        self.git_manager = GitManager(repo_path=GIT_REPO_PATH + datetime.now().strftime("%Y%m%d%H%M%S"))  # Use config
        self.state_file = os.path.join(self.git_manager.repo_path, 'vm_state.json')
        self.parameters_dir = os.path.join(self.git_manager.repo_path, 'parameters')
        os.makedirs(self.parameters_dir, exist_ok=True)

        # Register instruction handlers
        self.register_instruction('retrieve_knowledge_graph', self.instruction_handlers.retrieve_knowledge_graph_handler)
        self.register_instruction('retrieve_knowledge_embedded_chunks', self.instruction_handlers.retrieve_knowledge_embedded_chunks_handler)
        self.register_instruction('llm_generate', self.instruction_handlers.llm_generate_handler)
        self.register_instruction('condition', self.instruction_handlers.condition_handler)
        self.register_instruction('assign', self.instruction_handlers.assign_handler)
        self.register_instruction('reasoning', self.instruction_handlers.reasoning_handler)

    def set_goal(self, goal: str) -> None:
        if not isinstance(goal, str):
            self.logger.error("Goal must be a string.")
            self.state['errors'].append("Goal must be a string.")
            return
        self.state['goal'] = goal
        self.logger.info(f"Goal set: {goal}")

    def save_milestone(self, name: str, description: Optional[str] = None) -> None:
        if name in self.state['milestones']:
            self.logger.error(f"Milestone '{name}' already exists.")
            self.state['errors'].append(f"Milestone '{name}' already exists.")
            return
        if not isinstance(name, str):
            self.logger.error("Milestone name must be a string.")
            self.state['errors'].append("Milestone name must be a string.")
            return
        milestone = Milestone(
            name=name,
            variables=copy.deepcopy(self.variables),
            program_counter=self.state['program_counter'],
            description=description
        )
        self.state['milestones'][name] = milestone
        self.logger.info(f"Milestone '{name}' saved.")
        
        # Save milestone to file and commit the milestone to Git
        self.save_state()
        milestone_files = self.save_parameters("milestone", "output", {"name": name, "description": description})
        files_info = "\n".join([f"{k}: file path: {v}" for k, v in milestone_files.items()])
        original_message = f"Save milestone '{name}': {description or 'No description provided.'}"
        commit_message = f"{original_message}\n\nMilestone details stored in:\n{files_info}"
        if not self.git_manager.commit_changes(commit_message):
            self.logger.error("Failed to commit changes to Git.")
            # Handle the failure as needed

    def load_milestone(self, name: str) -> None:
        milestone = self.state['milestones'].get(name)
        if milestone:
            # Check dependencies
            for dep in milestone.dependencies:
                if dep not in self.state['milestones']:
                    self.logger.error(f"Dependency '{dep}' for milestone '{name}' is missing.")
                    self.state['errors'].append(f"Dependency '{dep}' for milestone '{name}' is missing.")
                    return
            self.variables = copy.deepcopy(milestone.variables)
            self.state['program_counter'] = milestone.program_counter
            self.logger.info(f"Milestone '{name}' loaded.")
            
            # Commit the load action to Git
            commit_message = f"Load milestone '{name}'."
            if not self.git_manager.commit_changes(commit_message):
                self.logger.error("Failed to commit changes to Git.")
                # Handle the failure as needed
        else:
            self.logger.error(f"Milestone '{name}' does not exist.")
            self.state['errors'].append(f"Milestone '{name}' does not exist.")

    def resolve_parameter(self, param):
        if isinstance(param, dict) and 'var' in param:
            var_name = param['var']
            value = self.variables.get(var_name)
            self.logger.info(f"Resolved variable '{var_name}' to value: {value}")
            return value
        elif isinstance(param, str):
            return interpolate_variables(param, self.variables)
        else:
            return param

    def execute_step_handler(self, step: Dict[str, Any]) -> bool:
        step_type = step.get('type')
        params = step.get('parameters', {})
        if not isinstance(step_type, str):
            self.logger.error("Invalid step type.")
            self.state['errors'].append("Invalid step type.")
            return False
        handler = getattr(self.instruction_handlers, f"{step_type}_handler", None)
        if handler:
            # Save input parameters
            input_files = self.save_parameters(step_type, "input", params)
            
            success = handler(params)
            
            # Save output parameters
            output_params = {k: v for k, v in self.variables.items() if k in params.get('output_var', [])}
            output_files = self.save_parameters(step_type, "output", output_params)
            
            # Prepare commit message
            commit_message = f"[{step_type}] - Executed step\n\n"
            commit_message += "Input Parameters:\n"
            for k, v in params.items():
                value_preview = str(v)[:50] + '...' if len(str(v)) > 50 else str(v)
                commit_message += f"- {k}: {value_preview}, file path: {input_files[k]}\n"
            
            commit_message += "\nOutput Parameters:\n"
            for k, v in output_params.items():
                value_preview = str(v)[:50] + '...' if len(str(v)) > 50 else str(v)
                commit_message += f"- {k}: {value_preview}, file path: {output_files[k]}\n"
            
            if success:
                commit_message += f"\nAdditional Info:\nStep executed successfully."
            else:
                commit_message += f"\nAdditional Info:\nStep execution failed."
            
            if not self.git_manager.commit_changes(commit_message):
                self.logger.error("Failed to commit changes to Git.")
            
            return success
        else:
            self.logger.warning(f"Unknown instruction: {step_type}")
            return False

    def execute_plan(self, plan: List[Dict[str, Any]]) -> bool:
        self.logger.info("Starting plan execution.")
        for index, step in enumerate(plan):
            self.state['program_counter'] = index
            success = self.execute_step_handler(step)
            if not success:
                self.logger.error(f"Execution failed at step {index}.")
                self.state['errors'].append(f"Execution failed at step {index}.")
                
                # Commit the failure to Git
                commit_message = f"Execution failed at step {index}: {step.get('type')}"
                if not self.git_manager.commit_changes(commit_message):
                    self.logger.error("Failed to commit changes to Git.")
                    # Handle the failure as needed
                
                return False
            if self.state['goal_completed']:
                self.logger.info("Goal completed during plan execution.")
                
                # Commit goal completion to Git
                commit_message = "Goal completed successfully."
                if not self.git_manager.commit_changes(commit_message):
                    self.logger.error("Failed to commit changes to Git.")
                    # Handle the failure as needed
                
                return True
        self.logger.info("Plan executed successfully.")
        
        # Commit successful plan execution to Git
        commit_message = "Plan executed successfully."
        if not self.git_manager.commit_changes(commit_message):
            self.logger.error("Failed to commit changes to Git.")
            # Handle the failure as needed
        
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
        with open('spec.md', 'r') as file:
            prompt += "the content of spec.md is:\n\n" + file.read()

        plan_response = self.llm_interface.generate(prompt)
        
        if not plan_response:
            self.logger.error("LLM failed to generate a response.")
            self.state['errors'].append("LLM failed to generate a response.")
            return False
        
        plan = parse_plan(plan_response)
        
        if plan:
            # Ensure you're on the 'main' branch before creating a new branch
            if not self.git_manager.checkout_branch('main'):  
                self.logger.error("Failed to checkout 'main' branch.")
                return False

            # Create a new branch off 'main'
            branch_name = f"plan_{len(self.state['previous_plans'])}"
            if not self.git_manager.create_branch(branch_name):
                self.logger.error(f"Failed to create branch '{branch_name}'.")
                return False

            if not self.git_manager.checkout_branch(branch_name):
                self.logger.error(f"Failed to checkout branch '{branch_name}'.")
                return False

            # Save the plan and commit
            self.state['current_plan'] = plan
            self.state['previous_plans'].append(plan)
            self.save_milestone("AfterPlanGeneration")
            self.logger.info("Plan generated and parsed successfully.")

            # Save plan to file and commit the generated plan to Git
            self.save_state()
            plan_files = self.save_parameters("generated_plan", "output", {"plan": plan})
            files_info = "\n".join([f"{k}: file path: {v}" for k, v in plan_files.items()])
            original_message = f"Generated new plan on branch '{branch_name}':\n{json.dumps(plan, indent=2)}"
            commit_message = f"{original_message}\n\nPlan stored in:\n{files_info}"
            if not self.git_manager.commit_changes(commit_message):
                self.logger.error("Failed to commit changes to Git.")

            return True
        else:
            self.logger.error("Failed to parse the generated plan.")
            self.state['errors'].append("Failed to parse the generated plan.")
            return False

    def adjust_plan(self) -> bool:
        self.logger.info("Adjusting plan based on errors and context.")
        context_info = {
            'errors': self.state['errors'],
            'milestones': list(self.state['milestones'].keys()),
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

        with open('spec.md', 'r') as file:
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
                # Handle the failure as needed
                return False

            if not self.git_manager.checkout_branch(branch_name):
                self.logger.error(f"Failed to checkout branch '{branch_name}'.")
                # Handle the failure as needed
                return False

            # Save the adjusted plan and commit
            self.state['current_plan'] = new_plan
            self.state['previous_plans'].append(new_plan)
            self.save_milestone("AfterPlanAdjustment")
            self.state['errors'] = []
            self.logger.info("Plan adjusted successfully.")

            # Commit the adjusted plan to Git
            commit_message = f"Adjusted plan on branch '{branch_name}':\n{json.dumps(new_plan, indent=2)}"
            if not self.git_manager.commit_changes(commit_message):
                self.logger.error("Failed to commit changes to Git.")
                # Handle the failure as needed

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
            self.save_milestone("AfterPlanUpdate")
            self.logger.info("Plan updated successfully.")
            
            # Commit the updated plan to Git
            commit_message = f"Updated plan:\n{json.dumps(new_plan, indent=2)}"
            if not self.git_manager.commit_changes(commit_message):
                self.logger.error("Failed to commit changes to Git.")
                # Handle the failure as needed
        else:
            self.logger.info("No changes to the current plan.")

    def run(self) -> None:
        max_iterations = 5
        iterations = 0

        # Example: Pull latest changes before starting
        self.pull_changes()

        while not self.state['goal_completed'] and iterations < max_iterations:
            self.logger.info(f">>>>>>>>>>>>>>>>>>>>Iteration {iterations}>>>>>>>>>>>>>>>>>>>")

            # Save iteration start to file and commit the start of a new iteration
            self.save_state()
            iteration_files = self.save_parameters("iteration_start", "output", {"iteration": iterations})
            files_info = "\n".join([f"{k}: file path: {v}" for k, v in iteration_files.items()])
            original_message = f"Starting iteration {iterations}."
            commit_message = f"{original_message}\n\nIteration details stored in:\n{files_info}"
            if not self.git_manager.commit_changes(commit_message):
                self.logger.error("Failed to commit changes to Git.")
                # Handle the failure as needed

            iterations += 1

            if not self.state['goal']:
                self.logger.error("No goal is set.")
                self.state['errors'].append("No goal is set.")
                
                # Commit the error to Git
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
                commit_message = "Execution failed. Initiating plan adjustment."
                if not self.git_manager.commit_changes(commit_message):
                    self.logger.error("Failed to commit changes to Git.")
                    # Handle the failure as needed
                
                adjust_success = self.adjust_plan()
                if not adjust_success:
                    self.logger.error("Failed to adjust the plan. Stopping execution.")
                    self.state['errors'].append("Failed to adjust the plan. Stopping execution.")
                    
                    # Commit the adjustment failure to Git
                    commit_message = "Failed to adjust the plan. Stopping execution."
                    if not self.git_manager.commit_changes(commit_message):
                        self.logger.error("Failed to commit changes to Git.")
                        # Handle the failure as needed
                    
                    break
                
            if self.state['goal_completed']:
                self.logger.info("Goal achieved successfully.")
                
                # Commit goal achievement to Git
                self.save_state()
                commit_message = "Goal achieved successfully."
                if not self.git_manager.commit_changes(commit_message):
                    self.logger.error("Failed to commit changes to Git.")
                    # Handle the failure as needed
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

        result = self.variables.get('result')
        if result:
            result = interpolate_variables(result, self.variables)
            print(f"\nFinal Result: {result}")
        else:
            print("\nNo result was generated.")

        # Example: Push changes after running the plan
        self.push_changes("Update milestones and plans after plan execution.")

    def reset_state(self) -> None:
        self.variables = {}
        self.state['program_counter'] = 0
        self.state['errors'] = []
        self.state['goal_completed'] = False
        self.logger.info("State has been reset.")

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

    def get_current_state(self) -> Dict[str, Any]:
        """
        Returns the current state of the VM.
        """
        return {
            'variables': self.variables,
            'state': self.state,
            'program_counter': self.state['program_counter'],
            'errors': self.state['errors'],
            'goal': self.state['goal'],
            'current_plan': self.state['current_plan'],
            'goal_completed': self.state['goal_completed']
        }

    def save_milestone_to_file(self, name: str, filepath: str) -> None:
        milestone = self.state['milestones'].get(name)
        if milestone:
            with open(filepath, 'w') as file:
                json.dump(milestone.__dict__, file, default=str, indent=2)
            self.logger.info(f"Milestone '{name}' saved to {filepath}.")
        else:
            self.logger.error(f"Milestone '{name}' does not exist. Cannot save to file.")

    def load_milestone_from_file(self, filepath: str) -> None:
        try:
            with open(filepath, 'r') as file:
                data = json.load(file)
            milestone = Milestone(**data)
            self.state['milestones'][milestone.name] = milestone
            self.logger.info(f"Milestone '{milestone.name}' loaded from {filepath}.")
        except Exception as e:
            self.logger.error(f"Failed to load milestone from {filepath}: {e}")
            self.state['errors'].append(f"Failed to load milestone from {filepath}: {e}")

    def push_changes(self, commit_message: str) -> None:
        success = self.git_manager.push_changes(commit_message)
        if success:
            self.logger.info("Changes pushed to remote repository successfully.")
        else:
            self.logger.error("Failed to push changes to remote repository.")

    def pull_changes(self) -> None:
        success = self.git_manager.pull_changes()
        if success:
            self.logger.info("Changes pulled from remote repository successfully.")
        else:
            self.logger.error("Failed to pull changes from remote repository.")

    def save_plan_to_file(self, filepath: str) -> None:
        with open(filepath, 'w') as file:
            json.dump(self.state['current_plan'], file, indent=2)
        self.logger.info(f"Plan saved to {filepath}.")
        
        # Commit the plan file to Git
        commit_message = f"Saved current plan to {filepath}."
        if not self.git_manager.commit_changes(commit_message):
            self.logger.error("Failed to commit changes to Git.")
            # Handle the failure as needed

    def load_plan_from_file(self, filepath: str) -> None:
        try:
            with open(filepath, 'r') as file:
                plan = json.load(file)
            self.state['current_plan'] = plan
            self.logger.info(f"Plan loaded from {filepath}.")
            
            # Commit the plan load action to Git
            commit_message = f"Loaded plan from {filepath}."
            if not self.git_manager.commit_changes(commit_message):
                self.logger.error("Failed to commit changes to Git.")
                # Handle the failure as needed
        except Exception as e:
            self.logger.error(f"Failed to load plan from {filepath}: {e}")
            self.state['errors'].append(f"Failed to load plan from {filepath}: {e}")

    def tag_plan_version(self, version_label: str) -> None:
        commit_message = f"Tagging plan version: {version_label}"
        if self.git_manager.run_command(['git', 'tag', version_label]):
            self.git_manager.commit_changes(commit_message)
        else:
            self.logger.error(f"Failed to tag plan version {version_label}.")

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

    def save_state(self):
        with open(self.state_file, 'w') as f:
            json.dump(self.state, f, indent=2, default=str)
        self.git_manager.run_command(['git', 'add', self.state_file])

    def save_parameters(self, step_type: str, io_type: str, params: Dict[str, Any]) -> Dict[str, str]:
        saved_files = {}
        for key, value in params.items():
            filename = f"{step_type}_{io_type}_{key}"
            filepath = os.path.join(self.parameters_dir, filename)
            with open(filepath, 'w') as f:
                if isinstance(value, (dict, list)):
                    json.dump(value, f, indent=2, default=str)
                else:
                    f.write(str(value))
            saved_files[key] = filename
        return saved_files

    def load_parameters(self, filepaths: Dict[str, str]) -> Dict[str, Any]:
        loaded_params = {}
        for key, filepath in filepaths.items():
            with open(filepath, 'r') as f:
                content = f.read()
                try:
                    loaded_params[key] = json.loads(content)
                except json.JSONDecodeError:
                    loaded_params[key] = content
        return loaded_params

if __name__ == "__main__":
    vm = PlanExecutionVM()
    vm.set_goal("summary the performance improvement of tidb from version 6.5 to newest version")
    
    if vm.generate_plan():
        print("Generated Plan:")
        print(json.dumps(vm.state['current_plan'], indent=2))
        vm.run()
    else:
        print("Failed to generate plan.")