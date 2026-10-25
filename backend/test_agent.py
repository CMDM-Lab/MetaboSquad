import json
import time
import uuid
from datetime import datetime

from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Prompt

from langchain_core.messages import HumanMessage
from langchain_core.callbacks.usage import get_usage_metadata_callback
from src.graph_agent.supervisor import build_main_graph


# ── Load environment variables and initialise the Rich console and agent ─────────────────────
load_dotenv()
console = Console()
main_graph = build_main_graph()


def print_agent_log(data: dict):
    """Parse and display the agent's execution flow and results"""
    if not data:
        console.print("[bold red]❌ 未取得 Agent 執行結果資料[/bold red]")
        return

    # 1. Show the todo status
    if 'todos' in data and data['todos']:
        todo_table = Table(title="📌 Current To-Do List", show_header=True, header_style="bold magenta")
        todo_table.add_column("Task Content", style="dim")
        todo_table.add_column("Status", justify="center")
        for todo in data['todos']:
            status_color = "green" if todo.get('status') == 'completed' else "yellow"
            todo_table.add_row(todo.get('content', ''), f"[{status_color}]{todo.get('status', '')}[/]")
        console.print(todo_table)

    # 2. Parse the message flow
    console.print("\n[bold cyan]🤖 Agent Execution Flow:[/bold cyan]")
    
    for msg in data.get('messages', []):
        msg_type = msg.__class__.__name__
        name = getattr(msg, 'name', 'User')
        
        # Handle tool calls (tools the agent decided to use)
        if hasattr(msg, 'tool_calls') and msg.tool_calls:
            for tool in msg.tool_calls:
                console.print(Panel(
                    f"[bold yellow]Tool Call:[/bold yellow] {tool['name']}\n"
                    f"[bold yellow]Args:[/bold yellow] {json.dumps(tool['args'], ensure_ascii=False, indent=2)}",
                    title=f"🛠️ {name} is calling a tool",
                    border_style="yellow"
                ))

        # Handle tool messages (results returned by tools)
        elif msg_type == "ToolMessage":
            content = msg.content if len(msg.content) < 500 else msg.content[:500] + "..."
            console.print(Panel(
                content,
                title=f"✅ Tool Result: {getattr(msg, 'name', 'Tool')}",
                border_style="green"
            ))

        # Handle the human message
        elif msg_type == "HumanMessage":
            console.print(Panel(msg.content, title="👤 Human Input", border_style="blue"))

        # Handle the final AI message
        elif msg_type == "AIMessage" and msg.content:
            console.print(Panel(msg.content, title="✨ Final AI Response", border_style="bold purple"))


def run(message: str, files: list[str] | None = None, thread_id: str | None = None) -> dict:
    """
    Run the main graph (main_graph) and report elapsed time and token usage
    """
    if thread_id is None:
        thread_id = str(uuid.uuid4())[:8]

    console.print(f"\n[bold green]🚀 開始執行任務... (Thread ID: {thread_id})[/bold green]")
    console.print(f"[bold white]提示詞：[/bold white]{message}")
    if files:
        console.print(f"[bold white]附加檔案：[/bold white]{files}")

    start_time = time.perf_counter()

    try:
        with get_usage_metadata_callback() as cb:
            result = main_graph.invoke(
                {
                    "messages": [HumanMessage(content=message)],
                    "files": files or [],
                    "date": datetime.now().strftime("%Y-%m-%d-%H-%M-%S"),
                },
                config={"configurable": {"thread_id": thread_id}},
            )
        
        end_time = time.perf_counter()
        elapsed = end_time - start_time

        # Print the detailed execution log
        print_agent_log(result)

        # Print execution timing and token statistics
        console.print("\n[bold yellow]⏱️  === E2E 執行時間 ===[/bold yellow]")
        console.print(f"總耗時: [bold green]{elapsed:.2f}[/bold green] 秒")

        console.print("\n[bold yellow]📊 === Token 用量統計 ===[/bold yellow]")
        if cb.usage_metadata:
            for model_name, usage in cb.usage_metadata.items():
                console.print(
                    f"[{model_name}] input={usage.get('input_tokens', 0)}, "
                    f"output={usage.get('output_tokens', 0)}, "
                    f"total={usage.get('total_tokens', 0)}"
                )
        else:
            console.print("無 Token 統計數據")

        return result

    except Exception as e:
        console.print(f"[bold red]❌ 執行過程中發生錯誤:[/bold red] {e}")
        return {}


def show_menu():
    """Display the console menu"""
    table = Table(title="🤖 Agent 測試控制台 (Interactive Runner)", show_header=True, header_style="bold cyan")
    table.add_column("選項", justify="center", style="bold yellow", width=8)
    table.add_column("測試內容說明", style="white")

    table.add_row("1", "💬 自訂對話（手動輸入問題與檔案路徑）")
    table.add_row("2", "❓ 測試：詢問能力（請問你可以幫我做甚麼?）")
    table.add_row("3", "📚 測試：文獻搜尋（請幫我搜尋酒精跟乳癌相關的文獻）")
    table.add_row("4", "📊 測試：CSV 分組分析（lcms_table.csv）")
    table.add_row("5", "🖼️ 測試：圖片評估（benchmark_semantic_pca_01.png）")
    table.add_row("6", "🧪 測試：資料查詢 + 圖片綜合評估（Dopamine + 圖片）")
    table.add_row("0", "❌ 離開程式")

    console.print("\n")
    console.print(table)


def main():
    while True:
        show_menu()
        choice = Prompt.ask("\n請選擇執行項目", choices=["0", "1", "2", "3", "4", "5", "6"], default="1")

        if choice == "0":
            console.print("[bold green]👋 測試結束！[/bold green]")
            break

        elif choice == "1":
            message = Prompt.ask("\n[bold cyan]請輸入要問 Agent 的問題[/bold cyan]")
            file_input = Prompt.ask("[bold cyan]請輸入檔案路徑 (有多個請以半角逗號分割，無檔案請直接按 Enter)[/bold cyan]", default="")
            
            files = [f.strip() for f in file_input.split(",") if f.strip()] if file_input else None
            run(message=message, files=files)
        
        elif choice == "2":
            run(message="請問你可以幫我做甚麼?")

        elif choice == "3":
            run(message="請幫我搜尋酒精跟乳癌相關的文獻")

        elif choice == "4":
            run(
                message="我的分組名稱是Label，不是配對樣本，樣本是離散，請幫我分析",
                files=["uploads/csv/lcms_table.csv"]
            )

        elif choice == "5":
            run(
                message="幫我評估這張圖適不適合科學發表",
                files=["uploads/image/benchmark_semantic_pca_01.png"]
            )

        elif choice == "6":
            run(
                message="請幫我搜尋 Dopamine 的詳細資料，並且幫我評估 uploads/image/benchmark_semantic_pca_01.png 這張圖",
                files=["uploads/image/benchmark_semantic_pca_01.png"]
            )

        # Pause after each run; press Enter to return to the main menu
        Prompt.ask("\n[dim]按下 Enter 鍵返回主選單...[/dim]", default="")


if __name__ == "__main__":
    main()