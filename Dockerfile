# Lightweight Python container for the ABCL/c+ runtime.
# Builds the Python ABCL/c+ interpreter + every AI provider SDK we
# integrate with.  No Gemini / Anthropic / OpenAI key is baked in;
# pass them at run time via -e or --env-file.

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install runtime deps in a single layer.
COPY src/python-abcl/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Copy source.  We keep only the Python implementation in the image;
# the OCaml binary needs an OCaml toolchain that the user can layer
# on if they want it.
COPY src/python-abcl /app/python-abcl

WORKDIR /app/python-abcl

# Default port for both the gateway and (optionally) the dashboard.
EXPOSE 8080

# Useful for orchestrators that probe live readiness:
HEALTHCHECK --interval=10s --timeout=2s --retries=3 \
  CMD python3 -c "import urllib.request, sys; \
    sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/healthz', timeout=1).status==200 else 1)" \
  || exit 1

# Default entrypoint runs whatever .abcl program the user mounts in.
# Override CMD to run a different sample.  Examples:
#   docker run -p 8080:8080 abcl /app/python-abcl/samples-remote/server.abcl
#   docker run -it abcl                       # interactive REPL
ENTRYPOINT ["python3", "abcl_main.py"]
CMD ["samples-remote/server.abcl"]
