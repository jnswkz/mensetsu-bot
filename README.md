# Mensetsu Bot

AI interview backend built with FastAPI, MongoDB Atlas Vector Search, and LiteLLM.

The service reads candidate profiles from MongoDB, retrieves similar seed questions from a question bank using embeddings, and generates tailored interview content such as:

- opening greetings
- fresh interview questions
- follow-up questions based on the candidate's last answer

## Features

- Candidate-aware interview generation from `candidate_profiles`
- Vector search over `question_banking`
- Structured question output with rubric and follow-ups
- Duplicate filtering before saving generated questions
- Small, service-oriented project layout under `services/`

## Tech Stack

- Python 3.13+
- FastAPI
- MongoDB / PyMongo
- MongoDB Atlas Vector Search
- LiteLLM
- OpenAI-compatible models for generation and embeddings

## Project Structure

```text
mensetsu-bot/
|-- main.py
|-- services/
|   |-- app.py
|   |-- config.py
|   |-- db.py
|   |-- bot/
|   |   `-- response.py
|   `-- interview/
|       |-- __init__.py
|       |-- candidate_pipeline.py
|       |-- models.py
|       `-- question_bank.py
|-- pyproject.toml
`-- README.md
```

## Environment Variables

Create a `.env` file in the project root:

```env
OAI_API_KEY=your_openai_or_compatible_key
MONGODB_URI=your_mongodb_connection_string
```

## Install

Using `uv`:

```bash
uv sync
```

Using `pip`:

```bash
pip install -e .
```

## Run

```bash
uv run python main.py
```

The API will start on `http://0.0.0.0:8000`.

## API Endpoints

### `GET /`

Health-style test endpoint.

Example:

```bash
curl "http://localhost:8000/"
```

### `GET /candidate_questions`

Generate interview questions for a candidate profile.

Query params:

- `user_id`: candidate `userId` or Mongo `_id`
- `round_name`: interview round name, default `technical_screen`
- `n`: number of questions, default `3`
- `save`: whether to save generated questions into `generated_questions`

Example:

```bash
curl "http://localhost:8000/candidate_questions?user_id=69de0d2317c28e9c3ca8b5f2&round_name=technical_screen&n=3&save=false"
```

### `POST /audio/transcriptions`

Upload an audio file and get transcript text back. The default model is `whisper-1`.

```bash
curl -X POST "http://localhost:8000/audio/transcriptions?model=whisper-1&language=en" ^
  -F "file=@candidate-answer.webm"
```

### `POST /audio/transcriptions/stream`

Upload a completed audio recording and receive server-sent transcript events. Use a streaming-capable transcription model such as `gpt-4o-mini-transcribe`.

```bash
curl -N -X POST "http://localhost:8000/audio/transcriptions/stream?model=gpt-4o-mini-transcribe&language=en" ^
  -F "file=@candidate-answer.webm"
```

### `POST /audio/speech`

Stream text-to-speech audio for any text. The response body is audio bytes, so write it to a file or pipe it to a player.

```bash
curl -X POST "http://localhost:8000/audio/speech" ^
  -H "Content-Type: application/json" ^
  -d "{\"text\":\"Welcome to the interview. Let's begin.\",\"voice\":\"coral\",\"response_format\":\"mp3\"}" ^
  --output speech.mp3
```

### `GET /candidate_questions/speech`

Generate candidate interview questions using the existing question pipeline, select one by `question_index`, and stream that question as spoken audio.

```bash
curl "http://localhost:8000/candidate_questions/speech?user_id=69de0d2317c28e9c3ca8b5f2&round_name=technical_screen&n=3&question_index=0&voice=coral" ^
  --output question.mp3
```

### SSE stream endpoints

Use these when the frontend wants server-sent JSON events instead of a single JSON response:

- `GET /candidate_questions_stream`
- `GET /follow_up_questions_stream`
- `GET /greeting_stream`

Example:

```bash
curl -N "http://localhost:8000/candidate_questions_stream?user_id=69de0d2317c28e9c3ca8b5f2&round_name=technical_screen&n=3"
```

### `GET /follow_up_questions`

Generate follow-up questions from the candidate's last answer.

Query params:

- `user_id`
- `last_question`
- `last_response`
- `end_round`: default `false`

Example:

```bash
curl --get "http://localhost:8000/follow_up_questions" ^
  --data-urlencode "user_id=69de0d2317c28e9c3ca8b5f2" ^
  --data-urlencode "last_question=Can you explain the difference between REST and GraphQL?" ^
  --data-urlencode "last_response=REST uses multiple endpoints while GraphQL uses a single endpoint and flexible queries." ^
  --data-urlencode "end_round=false"
```

### `GET /greeting`

Generate an interview opening greeting tailored to the candidate and round.

Query params:

- `user_id`
- `round_name`

Example:

```bash
curl "http://localhost:8000/greeting?user_id=69de0d2317c28e9c3ca8b5f2&round_name=technical_screen"
```

## MongoDB Collections

### `candidate_profiles`

The generation pipeline expects candidate profiles shaped roughly like:

```json
{
  "_id": "ObjectId",
  "userId": "ObjectId or string",
  "academicInfo": {
    "university": "University of Information Technology",
    "major": "Computer Science",
    "graduationYear": 2027,
    "gpa": 3.4
  },
  "achievements": [
    {
      "advantagePoint": "Fast learner and strong ownership mindset",
      "technicalSkills": ["Python", "MongoDB"],
      "softSkills": ["Communication", "Teamwork", "Problem solving"]
    }
  ],
  "projects": [],
  "workExperiences": [],
  "introductionQuestions": {
    "preferredRoles": [
      { "role": "Backend Engineer" },
      { "role": "Fullstack Developer" }
    ],
    "whyTheseRoles": "I enjoy solving system design and API problems.",
    "futureGoals": "Become a senior backend engineer in 3 years.",
    "favoriteTechnology": "TypeScript"
  }
}
```

### `question_banking`

Seed questions are stored with embeddings for vector retrieval.

Expected source shape:

```json
{
  "category": "Frontend",
  "question": "HTML Semantic la gi?",
  "suggestedAnswer": "La viec dung the HTML co y nghia ro rang...",
  "level": "Intern",
  "contributor": {
    "name": "SEeds Admin",
    "company": "UIT"
  },
  "isActive": true
}
```

The service enriches these documents with:

- `embedding`

### `generated_questions`

Generated interview questions are optionally saved here with:

- generated question payload
- `request_meta`
- `status: "draft"`

## How It Works

1. Load the candidate profile from `candidate_profiles`.
2. Infer category and level from the profile.
3. Extract technical skills, soft skills, and profile summary.
4. Embed a retrieval query and search `question_banking`.
5. Ask the generation model to create original questions inspired by the seeds.
6. Optionally reject near-duplicates and save the result.

## Vector Index

The service uses a MongoDB Atlas vector index named `question_bank_vector_idx_v2`.

Indexed fields:

- `embedding`
- `category`
- `level`
- `isActive`
- `contributor.company`

The index is created lazily by code in `services/interview/question_bank.py`.

## Notes

- The project currently uses `text-embedding-3-small` for embeddings.
- Question generation uses `openai/gpt-5.4-mini`.
- Candidate level and category are inferred heuristically from profile data.
- If the question bank is small or too strictly filtered, generation may fail with `No seed questions found`.

## Development

Quick syntax check:

```bash
python -m py_compile main.py services\app.py services\config.py services\db.py services\bot\response.py services\interview\__init__.py services\interview\models.py services\interview\question_bank.py services\interview\candidate_pipeline.py
```

## Future Improvements

- Move routes into dedicated FastAPI routers
- Add request/response models for API endpoints
- Add tests for candidate parsing and retrieval heuristics
- Add admin scripts for bulk question import
- Improve follow-up generation structured output
