"""A small client for Google Places API (New): type-ahead suggestions and their locations.

Only the two calls the app needs. Typing builds an autocomplete *session* (one
``session_token`` per search); fetching the chosen place's location with the same token
ends it, which is how Google bills autocomplete as one session rather than per keystroke.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx

BASE_URL = "https://places.googleapis.com/v1"
#: Bias suggestions towards London: Google allows a circle of up to 50 km.
LONDON_BIAS = {
    "circle": {"center": {"latitude": 51.5072, "longitude": -0.1276}, "radius": 50_000.0}
}
AUTOCOMPLETE_FIELDS = (
    "suggestions.placePrediction.placeId,"
    "suggestions.placePrediction.structuredFormat.mainText.text,"
    "suggestions.placePrediction.structuredFormat.secondaryText.text"
)
#: ``location`` alone is an Essentials field; ``displayName`` would bill at the Pro rate.
DETAILS_FIELDS = "location"


class PlacesError(Exception):
    """Google Places could not answer (network error, bad key, quota, unexpected reply)."""


@dataclass(frozen=True)
class PlacePrediction:
    """A suggested place: its id, and its name and area as Google formats them."""

    place_id: str
    name: str
    detail: str | None


class GooglePlaces:
    """Google Places API (New) over a shared ``httpx.AsyncClient``.

    Args:
        api_key: Sent in the ``X-Goog-Api-Key`` header; never leaves the server.
        http: The HTTP client to use (its lifetime is the caller's).

    """

    def __init__(self, api_key: str, http: httpx.AsyncClient) -> None:
        self._key = api_key
        self._http = http

    async def autocomplete(self, text: str, session_token: str) -> list[PlacePrediction]:
        """Suggest places in Great Britain matching ``text``, biased towards London."""
        body = {
            "input": text,
            "sessionToken": session_token,
            "includedRegionCodes": ["gb"],
            "languageCode": "en-GB",
            "locationBias": LONDON_BIAS,
        }
        raw = await self._request("POST", "/places:autocomplete", AUTOCOMPLETE_FIELDS, json=body)
        predictions = []
        for suggestion in raw.get("suggestions") or []:
            p = suggestion.get("placePrediction")
            if not p or not p.get("placeId"):
                continue
            fmt = p.get("structuredFormat") or {}
            predictions.append(
                PlacePrediction(
                    place_id=p["placeId"],
                    name=(fmt.get("mainText") or {}).get("text") or "",
                    detail=(fmt.get("secondaryText") or {}).get("text"),
                )
            )
        return predictions

    async def location(self, place_id: str, session_token: str) -> tuple[float, float]:
        """Return ``(lat, lon)`` of a suggested place, ending the autocomplete session."""
        raw = await self._request(
            "GET",
            f"/places/{quote(place_id, safe='')}",
            DETAILS_FIELDS,
            params={"sessionToken": session_token},
        )
        try:
            loc = raw["location"]
            return float(loc["latitude"]), float(loc["longitude"])
        except (KeyError, TypeError, ValueError) as exc:
            raise PlacesError(f"Google Places returned no location for {place_id}") from exc

    async def _request(self, method: str, path: str, fields: str, **kwargs: Any) -> Any:
        headers = {"X-Goog-Api-Key": self._key, "X-Goog-FieldMask": fields}
        try:
            response = await self._http.request(method, BASE_URL + path, headers=headers, **kwargs)
        except httpx.HTTPError as exc:
            raise PlacesError(f"Google Places request failed: {exc}") from exc
        if not response.is_success:
            raise PlacesError(
                f"Google Places returned {response.status_code}: {_message(response)}"
            )
        try:
            return response.json()
        except ValueError as exc:
            raise PlacesError("Google Places returned a response that is not JSON") from exc


def _message(response: httpx.Response) -> str:
    try:
        error = response.json().get("error") or {}
        return str(error.get("message") or response.reason_phrase)
    except (ValueError, AttributeError):
        return response.reason_phrase
