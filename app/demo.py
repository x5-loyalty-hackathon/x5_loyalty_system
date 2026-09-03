import json
import sys
from pathlib import Path

from app.contracts import RecommendationRequest
from app.main import recommendation_service


def main() -> None:
    request_path = Path(
        sys.argv[1] if len(sys.argv) > 1 else "examples/recommendation_request.json"
    )
    payload = json.loads(request_path.read_text(encoding="utf-8"))
    request = RecommendationRequest.model_validate(payload)
    response = recommendation_service.recommend(request)
    print(response.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
