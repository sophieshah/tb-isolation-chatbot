
FROM node:20-bookworm-slim

# Install Python and system dependencies
RUN apt-get update && apt-get install -y \
    python3 \
    python3-venv \
    python3-pip \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Node dependencies
COPY package*.json ./
RUN npm ci

# Install Python dependencies in an isolated environment
RUN python3 -m venv /opt/venv
ENV PYTHON_EXECUTABLE=/opt/venv/bin/python
ENV PATH="/opt/venv/bin:$PATH"

COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# Copy application
COPY . .

# Build frontend
RUN npm run build

ENV NODE_ENV=production

EXPOSE 10000

CMD ["npm", "start"]
