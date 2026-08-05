FROM python:3.11-slim

WORKDIR /octobot

RUN apt-get update && apt-get install -y git && \
    git clone --branch 2.0.16 https://github.com/Drakkar-Software/OctoBot.git . && \
    pip install --no-cache-dir -Ur requirements.txt

# SnipBot Security — منع السحب
RUN echo "WITHDRAWAL_ENABLED = False" >> octobot/constants.py && \
    echo "TRANSFER_ENABLED = False" >> octobot/constants.py

EXPOSE 5001

CMD ["python", "start.py", "--port", "5001"]
