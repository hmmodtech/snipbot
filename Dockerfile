FROM python:3.11-slim

WORKDIR /octobot

RUN apt-get update && apt-get install -y \
    git gcc g++ make libffi-dev libssl-dev \
    && rm -rf /var/lib/apt/lists/*

RUN git clone --depth 1 --branch 2.0.16 \
    https://github.com/Drakkar-Software/OctoBot.git .

RUN pip install --no-cache-dir psutil wheel setuptools && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir "octobot[full]==2.0.16"

RUN echo "WITHDRAWAL_ENABLED = False" >> octobot/constants.py && \
    echo "TRANSFER_ENABLED = False" >> octobot/constants.py

EXPOSE 5001

CMD ["python", "start.py", "--port", "5001"]
