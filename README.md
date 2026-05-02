# sandbox

Local HTTP sandbox for freeBBS agents. The API listens on `127.0.0.1`, starts a one-shot Docker container per request, disables container networking, and returns stdout, stderr, generated files, and the process exit code.

## Build

```bash
python -m pip install -r requirements.txt
make build
```

If your Docker network cannot reach Debian's default apt source, the image uses Aliyun mirrors by default. You can override them:

```bash
docker build \
  --build-arg DEBIAN_MIRROR=https://deb.debian.org/debian \
  --build-arg DEBIAN_SECURITY_MIRROR=https://deb.debian.org/debian-security \
  --build-arg PIP_INDEX_URL=https://pypi.org/simple \
  --build-arg TORCH_INDEX_URL=https://download.pytorch.org/whl/cpu \
  --build-arg TORCH_PACKAGE=torch==2.5.1+cpu \
  -t freebbs-sandbox-runner:latest sandbox_image
```

The sandbox image includes Python plus `numpy`, `pandas`, `scipy`, `sympy`, `matplotlib`, CPU-only `torch`, `gcc`, and `g++`.

## Run

```bash
make run
```

The service binds to `127.0.0.1:8000`. Requests from clients other than `127.0.0.1` are rejected by middleware as well.

## API

`POST /run`

```json
{
  "language": "python",
  "uid": "demo-user",
  "timeout": 10,
  "code": "print('hello')"
}
```

Supported languages are `python`, `c`, `cpp`, and `c++`.

Response:

```json
{
  "stdout": "hello\n",
  "stderr": "",
  "files": [],
  "exit_code": 0,
  "timed_out": false
}
```

Python plotting uses the non-GUI `Agg` backend. Any open matplotlib figures are saved as timestamped PNG files under `outputs/<uid>/`, and those paths are returned in `files`.

Example:

```bash
curl -s http://127.0.0.1:8000/run \
  -H 'content-type: application/json' \
  -d '{"language":"python","uid":"plot-demo","code":"import matplotlib.pyplot as plt\nplt.plot([1,2,3],[1,4,9])\nprint(\"done\")"}'
```

## Isolation

Each execution uses:

- `--network none`
- `--cap-drop ALL`
- `--security-opt no-new-privileges`
- memory, CPU, pid, and HTTP timeout limits
- a temporary workspace mounted only for the current job

Useful environment variables:

- `SANDBOX_IMAGE`, default `freebbs-sandbox-runner:latest`
- `SANDBOX_DEFAULT_TIMEOUT`, default `10`
- `SANDBOX_MAX_TIMEOUT`, default `30`
- `SANDBOX_MEMORY`, default `2g`
- `SANDBOX_CPUS`, default `2`
- `SANDBOX_MAX_CODE_BYTES`, default `262144`
