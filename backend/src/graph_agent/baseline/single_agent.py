"""Single-agent baseline for the controller comparison in the manuscript.

One ReAct-style agent (LangChain `create_agent`) gets the same tools as the
graph-based system and replaces the supervisor graph. The system prompt
names the task types but holds no per-task workflow.

By default each file in `skills/*.md` also becomes a tool that returns a
per-task workflow guide when the agent calls it (progressive disclosure).
This is the setting of the benchmark run in the manuscript. The tool counts
in the manuscript's Table 2 count task-tool calls only, not guide calls.
With `with_skills=False` the agent gets the task tools only.

Usage, from `backend/`:

    from src.graph_agent.baseline.single_agent import run
    run("Look up the PubChem CID and InChIKey of tryptophan")
    run("...", with_skills=False)
"""

import base64
import os
import re
from pathlib import Path
from typing import Dict, Tuple

from langchain.agents import create_agent
from langchain.chat_models import init_chat_model
from langchain.tools import tool
from langchain_core.messages import HumanMessage
from langchain_core.tools import StructuredTool

from src.graph_agent.baseline.log import print_agent_log
from src.graph_agent.baseline.prompts import SUPERVISOR_PROMPT_SKILL, SUPERVISOR_PROMPT_WORKFLOW
from src.graph_agent.tools import (
    edit_file, extract_significant, mummichog_analysis, pubchem_id_mapping,
    recommend_and_analysis, search_abstract, search_pubmed, write_file,
)
from src.graph_agent.use_tool.plot_tool import figure_compliance_checker, generate_figure_report

# Resolved from this file, not from the process working directory.
SKILLS_DIR = Path(__file__).resolve().parent / "skills"


@tool
def load_image_as_base64(path: str) -> str:
    """Convert the input path to a base64 string."""
    print(f"Reading image: {path}")
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


def create_agent_pure():
    """Agent with tools only; the workflows are written into the system prompt."""
    model = init_chat_model(model="gpt-4.1-mini", temperature=0)
    return create_agent(
        name="main_agent",
        system_prompt=SUPERVISOR_PROMPT_WORKFLOW,
        model=model,
        tools=[search_pubmed, search_abstract, edit_file, write_file, pubchem_id_mapping,
               mummichog_analysis, extract_significant, recommend_and_analysis, load_image_as_base64],
    )


def _parse_skill_file(filepath) -> Tuple[Dict[str, str], str]:
    """Split a skill file into its front matter (name, description) and body."""
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    blocks = re.split(r'^---+\s*$', content, flags=re.MULTILINE)

    metadata = {}
    main_content = ""

    if len(blocks) >= 3:
        for line in blocks[1].strip().split('\n'):
            if ':' in line:
                k, v = line.split(':', 1)
                metadata[k.strip()] = v.strip()
        main_content = blocks[2].strip()
    else:
        # No front matter: fall back to the file name
        filename = os.path.basename(filepath).replace(".md", "")
        metadata = {"name": filename, "description": f"Run the {filename} skill"}
        main_content = content

    return metadata, main_content


def _create_skill_tool(filepath) -> StructuredTool:
    """Wrap one skill file as a tool that returns the full guide when called."""
    metadata, main_content = _parse_skill_file(filepath)

    def fetch_skill_details() -> str:
        return f"【已成功載入 {metadata['name']} 技能詳細指引】\n請嚴格遵循以下步驟與規範：\n\n{main_content}"

    return StructuredTool.from_function(
        func=fetch_skill_details,
        name=metadata["name"],
        description=metadata["description"],
    )


def load_all_skills(skills_dir=SKILLS_DIR) -> list[StructuredTool]:
    """Build one tool per `.md` file in `skills_dir`."""
    skills_dir = Path(skills_dir)
    if not skills_dir.is_dir():
        raise FileNotFoundError(f"skill directory not found: {skills_dir}")
    return [_create_skill_tool(p) for p in sorted(skills_dir.glob("*.md"))]


def skill_agent_tools(with_skills: bool = True) -> list:
    """Tool registry of the baseline: the graph's tools, plus one tool per skill unless disabled."""
    base_tools = [
        search_pubmed, search_abstract, edit_file, write_file,
        pubchem_id_mapping, mummichog_analysis, extract_significant,
        recommend_and_analysis, load_image_as_base64, figure_compliance_checker, generate_figure_report,
    ]
    return base_tools + (load_all_skills() if with_skills else [])


def create_agent_skill(with_skills: bool = True):
    """The baseline that `run()` uses; see the module docstring for `with_skills`."""
    model = init_chat_model(model="gpt-4.1-mini", temperature=0)
    return create_agent(
        name="main_agent",
        system_prompt=SUPERVISOR_PROMPT_SKILL,
        model=model,
        tools=skill_agent_tools(with_skills),
    )


def run(message: str, files: list[str] | None = None, thread_id: str = "d",
        with_skills: bool = True) -> str:
    agent_skill = create_agent_skill(with_skills)
    result = agent_skill.invoke(
        {
            "messages": [HumanMessage(content=message)],
            "files": files or [],
        },
        config={"configurable": {"thread_id": thread_id}},
    )
    return print_agent_log(result)
