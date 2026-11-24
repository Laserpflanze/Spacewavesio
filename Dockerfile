FROM python:3.12-alpine

WORKDIR /app

COPY . .

# The Unity WebGL build files are too big for a phone/GitHub web upload,
# so they are fetched from the CrazyGames CDN during the Docker build.
# The CDN serves them uncompressed despite the .br names.
RUN mkdir -p Build && \
    wget -q -O Build/loader.js      "https://files.crazygames.com/space-waves/114/Build/f5621fc8e6401e7302a362d609e496a1.loader.js" && \
    wget -q -O Build/data.unityweb  "https://files.crazygames.com/space-waves/114/Build/1a568795816f05437ab0d4e6f50dc4ac.data.br" && \
    wget -q -O Build/wasm.wasm      "https://files.crazygames.com/space-waves/114/Build/c1aca0022182358dc43860f4ad8c934f.wasm.br" && \
    wget -q -O Build/framework.js   "https://files.crazygames.com/space-waves/114/Build/285f771aa266df412210c567c3f51a97.framework.js.br" && \
    ls -la Build/

ENV PORT=8080
EXPOSE 8080

CMD ["python3", "server.py"]
