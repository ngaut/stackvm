def tool(func):
    """
    Decorator to mark a function as a tool.
    """
    func.is_tool = True
    return func
