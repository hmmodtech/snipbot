FROM drakkarsoftware/octobot:2.0.16

# Copy default config into image
# This ensures settings persist even before Volume is populated
COPY user/config/config.json /octobot/user/config/config.json

EXPOSE 5001
