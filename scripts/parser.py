from __future__ import annotations

import argparse
import csv
import html
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urljoin
from urllib.request import Request, urlopen


DEFAULT_PAGE_URL = "https://2gis.kz/almaty/firm/70000001094769137/tab/reviews"
DEFAULT_OUTPUT_PATH = Path("data/raw_2gis_reviews.csv")
DEFAULT_API_KEY = "6e7e1929-4ea9-4a5d-8c05-d601860389bd"
USER_AGENT = (
	"Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
	"AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


@dataclass(frozen=True)
class ReviewExport:
	meta: dict[str, Any]
	reviews: list[dict[str, Any]]


def fetch_text(url: str) -> str:
	request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/json"})
	with urlopen(request, timeout=30) as response:
		return response.read().decode("utf-8", errors="replace")


def fetch_json(url: str) -> dict[str, Any]:
	request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
	with urlopen(request, timeout=30) as response:
		return json.loads(response.read().decode("utf-8", errors="replace"))


def extract_branch_id(page_url: str) -> str:
	match = re.search(r"/firm/(\d+)/tab/reviews", page_url)
	if not match:
		raise ValueError(f"Could not extract branch id from URL: {page_url}")
	return match.group(1)


def discover_api_url(page_url: str) -> str:
	page_html = fetch_text(page_url)
	page_html = html.unescape(page_html)

	api_match = re.search(
		r"https://public-api\.reviews\.2gis\.com/3\.0/branches/\d+/reviews\?[^\"'\s<]+",
		page_html,
	)
	if api_match:
		return api_match.group(0)

	branch_id = extract_branch_id(page_url)
	key_match = re.search(r"[?&]key=([0-9a-f-]{36})", page_html)
	api_key = key_match.group(1) if key_match else DEFAULT_API_KEY

	return (
		"https://public-api.reviews.2gis.com/3.0/branches/"
		f"{branch_id}/reviews?"
		"fields=meta.providers,meta.branch_rating,meta.branch_reviews_count,meta.total_count,"
		"reviews.hiding_reason,reviews.emojis,reviews.trust_factors"
		f"&is_advertiser=false&key={api_key}&limit=50&locale=ru_KZ&offset=0"
		"&rated=true&sort_by=friends"
	)


def iter_review_pages(start_url: str) -> Iterable[dict[str, Any]]:
	url = start_url
	while url:
		payload = fetch_json(url)
		yield payload
		next_url = payload.get("meta", {}).get("next_link")
		if not next_url or next_url == url:
			break
		url = urljoin(url, next_url)


def flatten_review(review: dict[str, Any]) -> dict[str, Any]:
	user = review.get("user") or {}
	trust_factors = (review.get("trust_factors") or {}).get("factors") or []
	trust_info = (review.get("trust_factors") or {}).get("trust_info") or {}
	first_factor = trust_factors[0] if trust_factors else {}

	return {
		"id": review.get("id"),
		"provider": review.get("provider"),
		"rating": review.get("rating"),
		"text": review.get("text"),
		"date_created": review.get("date_created"),
		"date_edited": review.get("date_edited"),
		"comments_count": review.get("comments_count"),
		"likes_count": review.get("likes_count"),
		"is_hidden": review.get("is_hidden"),
		"hiding_reason": review.get("hiding_reason"),
		"official_answer": review.get("official_answer"),
		"user": {
			"id": user.get("id"),
			"name": user.get("name"),
			"first_name": user.get("first_name"),
			"last_name": user.get("last_name"),
			"reviews_count": user.get("reviews_count"),
			"photo_64": (user.get("photo_preview_urls") or {}).get("64x64"),
		},
		"trust": {
			"confirmed_caption": trust_info.get("confirmed_caption"),
			"caption": trust_info.get("caption"),
			"visits_count": first_factor.get("visits_count"),
			"last_visit": first_factor.get("last_visit"),
			"factor_type": first_factor.get("type"),
		},
		"raw": review,
	}


def collect_reviews(page_url: str) -> ReviewExport:
	api_url = discover_api_url(page_url)
	pages = list(iter_review_pages(api_url))

	reviews: list[dict[str, Any]] = []
	seen_ids: set[str] = set()
	meta: dict[str, Any] = {}

	for page in pages:
		meta = page.get("meta", meta)
		for review in page.get("reviews", []):
			review_id = str(review.get("id"))
			if review_id in seen_ids:
				continue
			seen_ids.add(review_id)
			reviews.append(flatten_review(review))

	return ReviewExport(meta=meta, reviews=reviews)


def write_export(export: ReviewExport, output_path: Path) -> None:
	output_path.parent.mkdir(parents=True, exist_ok=True)
	payload = {
		"source": DEFAULT_PAGE_URL,
		"meta": export.meta,
		"review_count": len(export.reviews),
		"reviews": export.reviews,
	}
	output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def flatten_review_row(review: dict[str, Any]) -> dict[str, Any]:
	user = review.get("user") or {}
	trust = review.get("trust") or {}
	return {
		"id": review.get("id"),
		"provider": review.get("provider"),
		"rating": review.get("rating"),
		"text": review.get("text"),
		"date_created": review.get("date_created"),
		"date_edited": review.get("date_edited"),
		"comments_count": review.get("comments_count"),
		"likes_count": review.get("likes_count"),
		"is_hidden": review.get("is_hidden"),
		"hiding_reason": review.get("hiding_reason"),
		"official_answer": review.get("official_answer"),
		"user_id": user.get("id"),
		"user_name": user.get("name"),
		"user_first_name": user.get("first_name"),
		"user_last_name": user.get("last_name"),
		"user_reviews_count": user.get("reviews_count"),
		"user_photo_64": user.get("photo_64"),
		"trust_confirmed_caption": trust.get("confirmed_caption"),
		"trust_caption": trust.get("caption"),
		"trust_visits_count": trust.get("visits_count"),
		"trust_last_visit": trust.get("last_visit"),
		"trust_factor_type": trust.get("factor_type"),
	}


def write_csv_export(export: ReviewExport, output_path: Path) -> None:
	output_path.parent.mkdir(parents=True, exist_ok=True)
	rows = [flatten_review_row(review) for review in export.reviews]
	fieldnames = list(rows[0].keys()) if rows else []
	with output_path.open("w", encoding="utf-8", newline="") as csv_file:
		writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
		writer.writeheader()
		writer.writerows(rows)

def main() -> None:
	parser = argparse.ArgumentParser(description="Export all Steppe Coffee reviews from 2GIS.")
	parser.add_argument("--url", default=DEFAULT_PAGE_URL, help="2GIS reviews page URL")
	parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH), help="Path to the export file")
	parser.add_argument("--format", choices=("csv", "json"), default="csv", help="Export format")
	args = parser.parse_args()

	export = collect_reviews(args.url)
	output_path = Path(args.output)
	if args.format == "csv":
		write_csv_export(export, output_path)
	else:
		write_export(export, output_path)
	print(f"Saved {len(export.reviews)} reviews to {output_path}")


if __name__ == "__main__":
	main()
