FROM drakkarsoftware/octobot:stable

ENV OCTOBOT_PORT=5001

EXPOSE 5001

CMD ["python", "-m", "octobot", "--port", "5001"]
