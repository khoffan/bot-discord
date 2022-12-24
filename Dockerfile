FROM python:3.8

# Install required libraries
RUN pip install discord.py youtube_dl asyncio async_timeout

# Copy the code into the image
COPY . /app
WORKDIR /app

# Run the code when the container starts
CMD ["python", "bot.py"]
