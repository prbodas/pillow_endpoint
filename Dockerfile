FROM node:18-bullseye

# Install Python3, pip, ffmpeg for audio conversion, and helpers
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
    python3 python3-pip ffmpeg curl unzip ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# Python deps for ASR
RUN pip3 install --no-cache-dir vosk

# Download a small English Vosk model into the image
ENV VOSK_MODEL_DIR=/opt/vosk-model-small-en-us-0.15
RUN mkdir -p /opt \
 && curl -fsSL -o /tmp/vosk.zip https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip \
 && unzip -q /tmp/vosk.zip -d /opt \
 && rm -f /tmp/vosk.zip \
 && if [ ! -d "/opt/vosk-model-small-en-us-0.15" ]; then \
      mv /opt/*vosk-model-small-en-us* /opt/vosk-model-small-en-us-0.15 || true; \
    fi

WORKDIR /app

# Install Node deps
COPY package*.json ./
RUN npm ci --omit=dev || npm install --omit=dev

# Copy source
COPY . .

ENV PORT=8787
EXPOSE 8787

CMD ["node", "server.js"]

