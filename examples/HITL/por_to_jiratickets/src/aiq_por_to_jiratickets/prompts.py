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


PROMPT_EXTRACT_EPICS = """
    You are a project manager AI. You are given a chunk of a Plan of Record (POR).
    Extract any relevant Epics (major features), developer tasks, features and also bugs in the provided POR.
    Also extract the priorities (P0, P1 or P2) and link them to the corresponding epics, tasks, features and bugs.
    Format your answer as valid JSON with keys "epics", "tasks", "features" and "bugs".
    Epic: Represents a large, high-level project goal that can be broken down into smaller "features"
    Feature: A new functionality or major enhancement that adds a distinct capability to a product
    Task: Represents a single, specific action needed to complete a larger piece of work, like writing
    code for a particular function within a new feature

    Each "epic" item in the "epics" list should have: "name" and "description".
    Each "task" item in the "tasks" list should have: "title", "epic","storypoints", "description" optionally "owner" if identified.
    Each "bug" item in the "bugs" list should have: "title", "epic","storypoints", "description" optionally "owner" if identified.
    Each "feature" item in the "features" list should have: "title", "epic","storypoints", "description" optionally "owner" if identified.

    Assign story points for each task, bug and new feature based on complexity and effort. Provide the reasoning for
    assigning the story points in the corresponding description section

    Do not miss assigning any line item in the POR. Ensure every line item in POR gets assigned to epics or tasks or features or bugs.
    Example of desired JSON:
    {{
    "epics": [
        {{
        "name": "User Login System",
        "description": "Login/Authentication functionality supporting password and OAuth"
        }}
    ],
    "tasks": [
        {{
        "title": "Implement email+password login",
        "epic": "User Login System",
        "owner": "Alice"
        "priority": "P0"
        "storypoints": "8"
        "description": "Moderate complexity due to implementing secure authentication, input validation, hashing passwords, and managing sessions."
        }}
    ]
    "bugs": [
        {{
        "title": "Fix a bug related to authentication",
        "epic": "User Login System",
        "owner": "Alice"
        "priority": "P1"
        "storypoints": "6"
        "description": "Moderate complexity due to implementing secure authentication, input validation, hashing passwords, and managing sessions."
        }}
    ]
    "features": [
        {{
        "title": "Password reset functionality",
        "epic": "User Login System",
        "owner": "Alice"
        "priority": "P2"
        "storypoints": "7"
        "description": "Moderate complexity due to implementing password reset functionality"
        }}
    ]
    }}

    Return only valid JSON.
    Now process this PRD chunk:
    \"\"\"{por_content}\"\"\"
    """  # noqa: E501
