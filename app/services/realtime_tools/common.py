def success(message: str):
    return {
        "success": True,
        "message": message
    }


def failure(message: str):
    return {
        "success": False,
        "message": message
    }


def to_int_list(values):
    if not values:
        return []

    try:
        return [int(value) for value in values]
    except (ValueError, TypeError):
        return None