FROM drakkarsoftware/octobot:stable

EXPOSE 5001

ENTRYPOINT ["octobot"]
CMD ["--host", "0.0.0.0", "--port", "5001"]
