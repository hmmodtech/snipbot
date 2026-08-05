FROM python:3.10-slim-bookworm AS base

WORKDIR /octobot

RUN apt-get update && apt-get install -y \
    git gcc g++ make \
    libffi-dev libssl-dev \
    libxslt-dev libjpeg62-turbo-dev \
    zlib1g-dev libblas-dev liblapack-dev \
    libatlas-base-dev curl \
    && rm -rf /var/lib/apt/lists/*

RUN git clone --depth 1 --branch 2.0.16 \
    https://github.com/Drakkar-Software/OctoBot.git .

RUN pip install -U setuptools wheel "pip>=20.0.0" && \
    pip install --no-cache-dir --prefer-binary psutil && \
    pip install --no-cache-dir --prefer-binary -r requirements.txt && \
    pip install --no-cache-dir --prefer-binary -r full_requirements.txt && \
    python setup.py install

RUN echo "WITHDRAWAL_ENABLED = False" >> octobot/constants.py && \
    echo "TRANSFER_ENABLED = False" >> octobot/constants.py

EXPOSE 5001

CMD ["python", "start.py", "--port", "5001"]
