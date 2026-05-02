FROM python:3.12-slim

ARG DEBIAN_MIRROR=https://mirrors.aliyun.com/debian
ARG DEBIAN_SECURITY_MIRROR=https://mirrors.aliyun.com/debian-security
ARG PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple
ARG TORCH_INDEX_URL=https://download.pytorch.org/whl/cpu
ARG TORCH_PACKAGE=torch==2.5.1+cpu

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MPLBACKEND=Agg \
    DEBIAN_FRONTEND=noninteractive

RUN sed -i "s|http://deb.debian.org/debian-security|${DEBIAN_SECURITY_MIRROR}|g; s|http://deb.debian.org/debian|${DEBIAN_MIRROR}|g" /etc/apt/sources.list.d/debian.sources \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        gcc \
        g++ \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /tmp/sandbox-requirements.txt
RUN pip install --no-cache-dir -i "${PIP_INDEX_URL}" -r /tmp/sandbox-requirements.txt
RUN pip install --no-cache-dir \
    --timeout 60 \
    --retries 2 \
    --index-url "${TORCH_INDEX_URL}" \
    --extra-index-url "${PIP_INDEX_URL}" \
    "${TORCH_PACKAGE}" \
    || pip install --no-cache-dir -i "${PIP_INDEX_URL}" torch==2.5.1

COPY runner.py /usr/local/bin/sandbox-runner
RUN chmod +x /usr/local/bin/sandbox-runner \
    && useradd --create-home --shell /usr/sbin/nologin sandbox

USER sandbox
WORKDIR /workspace

ENTRYPOINT ["sandbox-runner"]
