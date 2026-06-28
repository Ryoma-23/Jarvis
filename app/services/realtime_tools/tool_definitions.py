REALTIME_TOOL_DEFINITIONS = [
    {
        "type": "function",
        "name": "add_note",
        "description": "ユーザーのメモを保存します。",
        "parameters": {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "保存するメモ内容"
                }
            },
            "required": ["content"]
        }
    },
    {
        "type": "function",
        "name": "list_notes",
        "description": "保存されているメモ一覧を取得します。",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "type": "function",
        "name": "search_notes",
        "description": "キーワードに一致するメモを検索します。",
        "parameters": {
            "type": "object",
            "properties": {
                "keyword": {
                    "type": "string",
                    "description": "検索キーワード"
                }
            },
            "required": ["keyword"]
        }
    },
    {
        "type": "function",
        "name": "delete_notes",
        "description": "指定した番号のメモを削除します。",
        "parameters": {
            "type": "object",
            "properties": {
                "note_ids": {
                    "type": "array",
                    "items": {
                        "type": "integer"
                    },
                    "description": "削除するメモIDの配列"
                }
            },
            "required": ["note_ids"]
        }
    },
    {
        "type": "function",
        "name": "add_task",
        "description": "ユーザーのタスクを追加します。",
        "parameters": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "追加するタスク名"
                },
                "due_date": {
                    "type": ["string", "null"],
                    "description": "期限。YYYY-MM-DD形式。なければnull"
                }
            },
            "required": ["title"]
        }
    },
    {
        "type": "function",
        "name": "list_tasks",
        "description": "保存されているタスク一覧を取得します。",
        "parameters": {
            "type": "object",
            "properties": {
                "status_filter": {
                    "type": "string",
                    "enum": ["all", "todo", "done"],
                    "description": "all=全件、todo=未完了、done=完了済み"
                }
            },
            "required": ["status_filter"]
        }
    },
    {
        "type": "function",
        "name": "search_tasks",
        "description": "キーワードに一致するタスクを検索します。",
        "parameters": {
            "type": "object",
            "properties": {
                "keyword": {
                    "type": "string",
                    "description": "検索キーワード"
                }
            },
            "required": ["keyword"]
        }
    },
    {
        "type": "function",
        "name": "complete_tasks",
        "description": "指定したタスクを完了にします。",
        "parameters": {
            "type": "object",
            "properties": {
                "task_ids": {
                    "type": "array",
                    "items": {
                        "type": "integer"
                    },
                    "description": "完了にするタスクIDの配列"
                }
            },
            "required": ["task_ids"]
        }
    },
    {
        "type": "function",
        "name": "delete_tasks",
        "description": "指定したタスクを削除します。",
        "parameters": {
            "type": "object",
            "properties": {
                "task_ids": {
                    "type": "array",
                    "items": {
                        "type": "integer"
                    },
                    "description": "削除するタスクIDの配列"
                }
            },
            "required": ["task_ids"]
        }
    },
    {
        "type": "function",
        "name": "add_memory",
        "description": "今後の会話で参考にする長期記憶を保存します。",
        "parameters": {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "保存する記憶内容"
                },
                "category": {
                    "type": "string",
                    "enum": ["profile", "preference", "goal", "project", "routine", "other"],
                    "description": "記憶カテゴリ"
                }
            },
            "required": ["content", "category"]
        }
    },
    {
        "type": "function",
        "name": "list_memory",
        "description": "保存されている長期記憶の一覧を取得します。",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "type": "function",
        "name": "search_memory",
        "description": "キーワードに一致する長期記憶を検索します。",
        "parameters": {
            "type": "object",
            "properties": {
                "keyword": {
                    "type": "string",
                    "description": "検索キーワード"
                }
            },
            "required": ["keyword"]
        }
    },
    {
        "type": "function",
        "name": "update_memory",
        "description": "指定した長期記憶を更新します。",
        "parameters": {
            "type": "object",
            "properties": {
                "memory_ids": {
                    "type": "array",
                    "items": {
                        "type": "integer"
                    },
                    "description": "更新する記憶IDの配列"
                },
                "content": {
                    "type": "string",
                    "description": "更新後の記憶内容"
                },
                "category": {
                    "type": ["string", "null"],
                    "enum": ["profile", "preference", "goal", "project", "routine", "other", None],
                    "description": "更新後のカテゴリ。変更しない場合はnull"
                }
            },
            "required": ["memory_ids", "content"]
        }
    },
    {
        "type": "function",
        "name": "delete_memory",
        "description": "指定した長期記憶を削除します。",
        "parameters": {
            "type": "object",
            "properties": {
                "memory_ids": {
                    "type": "array",
                    "items": {
                        "type": "integer"
                    },
                    "description": "削除する記憶IDの配列"
                }
            },
            "required": ["memory_ids"]
        }
    }
]