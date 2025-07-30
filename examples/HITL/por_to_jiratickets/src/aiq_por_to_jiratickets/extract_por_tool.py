# SPDX-FileCopyrightText: Copyright (c) 2025, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import json
import logging
import os
import re

from aiq.builder.builder import Builder
from aiq.builder.framework_enum import LLMFrameworkEnum
from aiq.builder.function_info import FunctionInfo
from aiq.cli.register_workflow import register_function
from aiq.data_models.component_ref import LLMRef
from aiq.data_models.function import FunctionBaseConfig

from .prompts import PROMPT_EXTRACT_EPICS

logger = logging.getLogger(__name__)


def correct_json_format(response):
    try:
        # Locate the JSON content (start from the first '{')
        json_start = response.find("{")
        if json_start == -1:
            raise ValueError("No JSON found in the response.")

        # Extract potential JSON part
        json_content = response[json_start:].strip()

        # Remove trailing markdown if present
        json_response = re.sub(r"```", "", json_content)

    except Exception as e:
        logger.exception("Error: %s", e, exc_info=True)
        json_response = response

    return json_response


def process_input_text(input_text):
    input_text = input_text.replace('Observ', "")
    input_text = re.sub(r"\s+", "", input_text)
    return input_text


class ExtractPORToolConfig(FunctionBaseConfig, name="extract_por_tool"):
    root_path: str
    llm: LLMRef


@register_function(config_type=ExtractPORToolConfig, framework_wrappers=[LLMFrameworkEnum.LANGCHAIN])
async def extract_from_por_tool(config: ExtractPORToolConfig, builder: Builder):
    """
    Extract epics and issues from the given PRO/PRD text using the LLM chain
    and store the result in session state.
    """

    from langchain.chains.llm import LLMChain
    from langchain.prompts import PromptTemplate

    llm = await builder.get_llm(llm_name=config.llm, wrapper_type=LLMFrameworkEnum.LANGCHAIN)
    prompt = PromptTemplate(
        input_variables=["por_content"],
        template=(PROMPT_EXTRACT_EPICS),
    )
    chain = LLMChain(llm=llm, prompt=prompt)

    async def _arun(input_text: str) -> str:

        # input_text = process_input_text(input_text)
        if os.path.isfile(config.root_path + input_text):
            logger.debug("Detected file: %s", config.root_path + input_text)

            with open(config.root_path + input_text, 'r', encoding='utf-8') as file:
                input_text = [line.strip() for line in file if line.strip()]

        response = await chain.arun(por_content=input_text)
        response = correct_json_format(response)
        # Attempt to parse the response as JSON. If it fails, just store the raw string.
        try:
            data = json.loads(response)
        except json.JSONDecodeError as e:
            logger.debug("An error occurred while loading Json %s", e)
            return "An error occurred while loading Json so please re-run extraction step again"

        filename = config.root_path + "epics_tasks.json"
        try:
            with open(filename, 'w', encoding='utf-8') as json_file:
                json.dump(data, json_file)
            logger.debug("Data successfully saved to %s", filename)

        except Exception as e:
            logger.exception("An error occurred while saving the file: %s", e, exc_info=True)

        return "Extraction complete. You can now ask me to show epics or tasks."

    yield FunctionInfo.from_fn(
        _arun,
        description=(
            "Use this to extract epics and tasks from POR content and assign story points. If the user provides the "
            "filename then pass that as input or if the user provides raw POR text then pass that as input"))


class ShowTicketsToolConfig(FunctionBaseConfig, name="show_jira_tickets"):
    root_path: str


@register_function(config_type=ShowTicketsToolConfig)
async def show_tickets_tool(config: ShowTicketsToolConfig, builder: Builder):
    """
    Return a string listing the epics from the last extraction.
    """
    filename = config.root_path + "epics_tasks.json"

    async def _arun(input_text: str) -> str:
        # input_text = process_input_text(input_text)
        try:
            with open(filename, 'r', encoding='utf-8') as json_file:
                data = json.load(json_file)
                logger.debug("Data successfully loaded from %s", filename)
        except Exception as e:
            logger.exception("An error occurred while loading the file: %s", e, exc_info=True)
            raise
        # If we have a "raw_response", it means we couldn't parse JSON
        if "raw_response" in data:
            return "Data wasn't in JSON format:\n" + data["raw_response"]
        if input_text in ['epics', 'bugs', 'tasks', 'features']:
            tickets = data.get(input_text, [])
            if not tickets:
                return "No epics found in the extracted data."

        lines = ["### Extracted " + str(input_text) + ":"]
        if input_text == 'epics':
            for i, epic in enumerate(tickets, start=1):
                lines.append(f"- **{input_text} {i}**: {epic.get('name', 'Unnamed Epic')}")
                lines.append(f"  - Description: {epic.get('description', 'N/A')}")
        elif input_text == 'bugs':
            for i, issue in enumerate(tickets, start=1):
                lines.append(f"- **{input_text} {i}**: {issue.get('title', 'Untitled Issue')}")
                lines.append(f"  - Epic Link: {issue.get('epic', 'No epic link')}")
                lines.append(f"  - Priority: {issue.get('description', 'N/A')}")
        elif input_text == 'tasks':
            for i, issue in enumerate(tickets, start=1):
                lines.append(f"- **{input_text} {i}**: {issue.get('title', 'Untitled Issue')}")
                lines.append(f"  - Epic Link: {issue.get('epic', 'No epic link')}")
                lines.append(f"  - Priority: {issue.get('description', 'N/A')}")
        elif input_text == 'features':
            for i, issue in enumerate(tickets, start=1):
                lines.append(f"- **{input_text} {i}**: {issue.get('title', 'Untitled Issue')}")
                lines.append(f"  - Epic Link: {issue.get('epic', 'No epic link')}")
                lines.append(f"  - Priority: {issue.get('description', 'N/A')}")
        else:
            lines = ["### Extracted Epics, tasks and bugs:"]
            tickets = data.get("epics", [])
            for i, epic in enumerate(tickets, start=1):
                lines.append(f"- **Epic {i}**: {epic.get('name', 'Unnamed Epic')}")
                lines.append(f"  - Description: {epic.get('description', 'N/A')}")
            tickets = data.get("tasks", [])
            for i, issue in enumerate(tickets, start=1):
                lines.append(f"- **Tasks {i}**: {issue.get('title', 'Untitled Issue')}")
                lines.append(f"  - Epic Link: {issue.get('epic', 'No epic link')}")
                lines.append(f"  - Priority: {issue.get('priority', 'N/A')}")
            tickets = data.get("bugs", [])
            for i, issue in enumerate(tickets, start=1):
                lines.append(f"- **Bugs {i}**: {issue.get('title', 'Untitled Issue')}")
                lines.append(f"  - Epic Link: {issue.get('epic', 'No epic link')}")
                lines.append(f"  - Priority: {issue.get('priority', 'N/A')}")
        return "\n".join(lines)

    yield FunctionInfo.from_fn(
        _arun,
        description=("Use this to display previously extracted epics or tasks or bugs oe features. "
                     "If the user asks shows epics, then pass epics as input or if user asks bugs pass "
                     "bugs as input and so on. If the user asks to to show all tickets pass all as input"))
