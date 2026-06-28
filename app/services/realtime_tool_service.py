from app.services.realtime_tools.tool_registry import TOOL_REGISTRY


def execute_realtime_tool(tool_name: str, arguments: dict):
    tool_function = TOOL_REGISTRY.get(tool_name)

    if not tool_function:
        return {
            "success": False,
            "message": f"未対応のtoolです: {tool_name}"
        }

    try:
        return tool_function(arguments)

    except Exception as error:
        return {
            "success": False,
            "message": f"tool実行中にエラーが発生しました: {str(error)}"
        }