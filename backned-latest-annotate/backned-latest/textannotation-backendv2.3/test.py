import vertexai
from vertexai.generative_models import GenerativeModel

vertexai.init(
    project="prod-y-in2300452",
    location="us-central1"
)

model = GenerativeModel("gemini-2.5-flash")

response = model.generate_content("Hello")
print(response.text)