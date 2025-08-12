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



ARG BASE
ARG PYTHON_PACKAGE_MANAGER

FROM node:22 as node

FROM ${BASE} as base

# ===== install common packages ==================================================================

RUN <<EOF

set -x

apt-get update;

rm -rf /tmp/*;
rm -rf /var/tmp/*;
rm -rf /var/cache/apt/*;
rm -rf /var/lib/apt/lists/*;

EOF


FROM base as uv-base

COPY --from=ghcr.io/astral-sh/uv:0.8.9 /uv /uvx /bin/

FROM ${PYTHON_PACKAGE_MANAGER}-base

ENV PATH="${PATH}:/home/coder/dev/nat/.devcontainer/bin"

ARG PYTHON_PACKAGE_MANAGER
ENV PYTHON_PACKAGE_MANAGER="${PYTHON_PACKAGE_MANAGER}"

ENV SCCACHE_REGION="us-east-2"
ENV SCCACHE_BUCKET="rapids-sccache-devs"
ENV AWS_ROLE_ARN="arn:aws:iam::279114543810:role/nv-gha-token-sccache-devs"
ENV HISTFILE="/home/coder/.cache/._bash_history"
