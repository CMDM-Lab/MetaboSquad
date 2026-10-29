"""Print the message trace of a baseline run to the console."""

import json

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()


def print_agent_log(data):
    # 1. To-do list, if the agent kept one
    if 'todos' in data:
        todo_table = Table(title="📌 Current To-Do List", show_header=True, header_style="bold magenta")
        todo_table.add_column("Task Content", style="dim")
        todo_table.add_column("Status", justify="center")
        for todo in data['todos']:
            status_color = "green" if todo['status'] == 'completed' else "yellow"
            todo_table.add_row(todo['content'], f"[{status_color}]{todo['status']}[/]")
        console.print(todo_table)

    # 2. Message flow
    console.print("\n[bold cyan]🤖 Agent Execution Flow:[/bold cyan]")

    for msg in data.get('messages', []):
        msg_type = msg.__class__.__name__
        name = getattr(msg, 'name', 'User')

        # Tool calls the agent decided to make
        if hasattr(msg, 'tool_calls') and msg.tool_calls:
            for tool in msg.tool_calls:
                console.print(Panel(
                    f"[bold yellow]Tool Call:[/bold yellow] {tool['name']}\n"
                    f"[bold yellow]Args:[/bold yellow] {json.dumps(tool['args'], ensure_ascii=False, indent=2)}",
                    title=f"🛠️ {name} is calling a tool",
                    border_style="yellow"
                ))

        # Tool results, truncated to keep the console readable
        elif msg_type == "ToolMessage":
            content = msg.content if len(msg.content) < 500 else msg.content[:500] + "..."
            console.print(Panel(
                content,
                title=f"✅ Tool Result: {msg.name}",
                border_style="green"
            ))

        elif msg_type == "HumanMessage":
            console.print(Panel(msg.content, title="👤 Human Input", border_style="blue"))

        # Final AI answer
        elif msg_type == "AIMessage" and msg.content:
            console.print(Panel(msg.content, title="✨ Final AI Response", border_style="bold purple"))
