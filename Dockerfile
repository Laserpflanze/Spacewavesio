FROM python:3.12-alpine

WORKDIR /app

COPY . .

# Game files are fetched at build time (too big for phone/GitHub web upload).
# fetch_build.py forces uncompressed transfer AND verifies the content,
# so a broken download fails the build instead of shipping corrupt JS.
RUN python3 fetch_build.py

ENV PORT=8080
EXPOSE 8080

CMD ["python3", "server.py"]
