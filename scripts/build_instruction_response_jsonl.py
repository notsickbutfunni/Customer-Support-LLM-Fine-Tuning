from __future__ import annotations

import argparse
import ast
import csv
import json
import random
import re
from pathlib import Path
from typing import Any


DEFAULT_INPUT_PATH = Path("data/raw_2gis_reviews.csv")
DEFAULT_OUTPUT_DIR = Path("data")
DEFAULT_OUTPUT_NAME = "instruction_response_dataset.jsonl"
DEFAULT_TEST_NAME = "instruction_response_test.jsonl"
DEFAULT_TRAIN_NAME = "instruction_response_train.jsonl"
DEFAULT_TEST_SIZE = 20
DEFAULT_MIN_WORDS = 2
DEFAULT_MIN_CHARS = 8
DEFAULT_SEED = 42

INSTRUCTION = "Write a polite customer-support reply from a cafe manager's perspective in Russian. Keep it professional, empathetic, and concise."


def normalize_text(text: str) -> str:
	return re.sub(r"\s+", " ", text.strip()).lower()


def word_count(text: str) -> int:
	return len([token for token in re.split(r"\s+", text.strip()) if token])


def is_low_quality(text: str, min_words: int, min_chars: int) -> bool:
	if not text:
		return True
	if len(text) < min_chars:
		return True
	if word_count(text) < min_words:
		return True
	if re.search(r"(.)\1{6,}", text):
		return True
	if re.fullmatch(r"[\W_]+", text):
		return True
	return False


def parse_official_answer(raw_answer: str) -> str:
	raw_answer = raw_answer.strip()
	if not raw_answer:
		return ""
	try:
		parsed = ast.literal_eval(raw_answer)
	except (ValueError, SyntaxError):
		return raw_answer
	if isinstance(parsed, dict):
		text = str(parsed.get("text", "")).strip()
		if text:
			return text
	return raw_answer


def build_template_response(rating: int, review_text: str) -> str:
	if rating >= 5:
		return (
			"Спасибо за теплый отзыв. Нам очень приятно, что вам понравились напитки, "
			"сервис и атмосфера. Будем рады видеть вас снова."
		)
	if rating == 4:
		return (
			"Спасибо за обратную связь. Рады, что вам в целом понравилось, и учтем "
			"ваше замечание, чтобы сделать сервис еще лучше."
		)
	if rating == 3:
		return (
			"Спасибо, что поделились впечатлением. Нам жаль, что визит получился не "
			"идеальным. Мы обязательно учтем замечания по сервису и качеству, чтобы "
			"улучшить опыт гостей."
		)
	if review_text:
		return (
			"Спасибо за честный отзыв. Нам жаль, что опыт оказался негативным. Мы "
			"передадим ваше замечание команде и постараемся разобраться в ситуации."
		)
	return "Спасибо за обратную связь. Мы передадим ваш отзыв команде и постараемся улучшить сервис."


def load_reviews(input_path: Path, min_words: int, min_chars: int) -> list[dict[str, Any]]:
	rows: list[dict[str, Any]] = []
	seen_texts: set[str] = set()
	with input_path.open(encoding="utf-8", newline="") as csv_file:
		reader = csv.DictReader(csv_file)
		for row in reader:
			text = str(row.get("text") or "").strip()
			if is_low_quality(text, min_words=min_words, min_chars=min_chars):
				continue
			key = normalize_text(text)
			if key in seen_texts:
				continue
			seen_texts.add(key)
			rows.append(row)
	return rows


def build_example(row: dict[str, Any]) -> dict[str, Any]:
	text = str(row.get("text") or "").strip()
	rating = int(row.get("rating") or 0)
	official_answer = parse_official_answer(str(row.get("official_answer") or ""))
	response = official_answer or build_template_response(rating, text)
	return {
		"instruction": INSTRUCTION,
		"input": text,
		"response": response,
	}


def split_examples(examples: list[dict[str, Any]], test_size: int, seed: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
	if len(examples) <= test_size:
		raise ValueError(f"Need more than {test_size} examples after filtering, got {len(examples)}")
	rng = random.Random(seed)
	shuffled = examples[:]
	rng.shuffle(shuffled)
	test_examples = shuffled[:test_size]
	train_examples = shuffled[test_size:]
	return train_examples, test_examples


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
	path.parent.mkdir(parents=True, exist_ok=True)
	with path.open("w", encoding="utf-8") as handle:
		for row in rows:
			handle.write(json.dumps(row, ensure_ascii=False))
			handle.write("\n")


def main() -> None:
	parser = argparse.ArgumentParser(description="Build an instruction-response JSONL dataset from 2GIS reviews.")
	parser.add_argument("--input", type=Path, default=DEFAULT_INPUT_PATH, help="Path to the parsed CSV reviews file")
	parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="Directory for JSONL output files")
	parser.add_argument("--dataset-name", default=DEFAULT_OUTPUT_NAME, help="Combined JSONL file name")
	parser.add_argument("--train-name", default=DEFAULT_TRAIN_NAME, help="Train JSONL file name")
	parser.add_argument("--test-name", default=DEFAULT_TEST_NAME, help="Test JSONL file name")
	parser.add_argument("--test-size", type=int, default=DEFAULT_TEST_SIZE, help="Number of held-out examples")
	parser.add_argument("--min-words", type=int, default=DEFAULT_MIN_WORDS, help="Minimum words required for a review")
	parser.add_argument("--min-chars", type=int, default=DEFAULT_MIN_CHARS, help="Minimum characters required for a review")
	parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help="Random seed for the train/test split")
	args = parser.parse_args()

	reviews = load_reviews(args.input, min_words=args.min_words, min_chars=args.min_chars)
	examples = [build_example(row) for row in reviews]
	train_examples, test_examples = split_examples(examples, test_size=args.test_size, seed=args.seed)

	combined_path = args.output_dir / args.dataset_name
	train_path = args.output_dir / args.train_name
	test_path = args.output_dir / args.test_name

	write_jsonl(combined_path, examples)
	write_jsonl(train_path, train_examples)
	write_jsonl(test_path, test_examples)

	print(f"Loaded {len(reviews)} cleaned reviews")
	print(f"Wrote {len(examples)} total examples to {combined_path}")
	print(f"Wrote {len(train_examples)} train examples to {train_path}")
	print(f"Wrote {len(test_examples)} test examples to {test_path}")


if __name__ == "__main__":
	main()