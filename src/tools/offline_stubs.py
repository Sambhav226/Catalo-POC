from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Type, TypeVar

from pydantic import BaseModel

from src.config import ROOT

T = TypeVar("T", bound=BaseModel)


def build_offline_response(model: Type[T], system: str, user: str) -> T:
    name = model.__name__
    if name == "CategorySchema":
        return _offline_category_schema(model, user)
    if name == "SpecExtraction":
        return _offline_spec_extraction(model, user)
    if name == "EnrichmentExtraction":
        return _offline_enrichment_extraction(model, user)
    return _blank_of(model)


def _offline_category_schema(model: Type[T], user: str) -> T:
    slug = _extract_slug(user) or "4k-led-tv"
    tpl_path = ROOT / "data" / "seed" / "schemas" / f"{slug}.template.json"
    if not tpl_path.exists():
        return _blank_of(model)
    tpl = json.loads(tpl_path.read_text(encoding="utf-8"))
    payload = {
        "category": tpl.get("category", "Unknown"),
        "version": "1.0.0",
        "fields": tpl["fields"],
        "induced_from": ["offline_template"],
    }
    return model.model_validate(payload)


def _offline_spec_extraction(model: Type[T], user: str) -> T:
    raw_specs = _extract_raw_specs(user)
    normalised = _normalise_specs(raw_specs)
    return model.model_validate({"fields": normalised})


def _offline_enrichment_extraction(model: Type[T], user: str) -> T:
    payload_text = _extract_json_block(user, marker="PAGE_TEXT")
    fields_wanted = _extract_wanted_fields(user)
    values: dict[str, Any] = {}
    for f in fields_wanted:
        v = _guess_from_text(f, payload_text)
        if v is not None:
            values[f] = v
    return model.model_validate({"fields": values})


def _blank_of(model: Type[T]) -> T:
    schema = model.model_json_schema()
    props = schema.get("properties", {})
    payload: dict[str, Any] = {}
    for key, spec in props.items():
        t = spec.get("type")
        if t == "array":
            payload[key] = []
        elif t == "object":
            payload[key] = {}
        elif t == "integer":
            payload[key] = 0
        elif t == "number":
            payload[key] = 0.0
        elif t == "boolean":
            payload[key] = False
        else:
            payload[key] = ""
    return model.model_validate(payload)


def _extract_slug(text: str) -> str | None:
    m = re.search(r"slug\s*[:=]\s*['\"]?([a-z0-9\-]+)", text, re.IGNORECASE)
    return m.group(1) if m else None


def _extract_raw_specs(text: str) -> dict[str, str]:
    m = re.search(r"RAW_SPECS_JSON\s*=\s*", text)
    if not m:
        return {}
    start = m.end()
    if start >= len(text) or text[start] != "{":
        return {}
    depth = 0
    end = start
    for i in range(start, len(text)):
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    blob = text[start:end]
    try:
        return json.loads(blob)
    except Exception:
        return {}


def _extract_wanted_fields(text: str) -> list[str]:
    m = re.search(r"WANTED_FIELDS\s*=\s*\[(.*?)\]", text, re.DOTALL)
    if not m:
        return []
    inner = m.group(1)
    return [s.strip().strip('"').strip("'") for s in inner.split(",") if s.strip()]


def _extract_json_block(text: str, marker: str) -> str:
    m = re.search(rf"{marker}\s*=\s*\"\"\"(.*?)\"\"\"", text, re.DOTALL)
    return m.group(1) if m else text


def _normalise_specs(raw: dict[str, str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if not raw:
        return out

    alias_map = {
        "brand": ["Brand"],
        "model_number": ["Model", "Model Number", "Model No"],
        "screen_size_inches": ["Screen Size", "Screen size (inch)", "Display Size"],
        "resolution": ["Resolution"],
        "resolution_pixels": ["Resolution", "Display resolution", "Resolution Standard"],
        "display_type": ["Display Type", "Display Technology", "Display"],
        "refresh_rate_hz": ["Refresh Rate"],
        "hdr_support": ["HDR"],
        "smart_tv": ["Smart TV", "Smart Tv"],
        "operating_system": ["Operating System", "OS"],
        "processor": ["Processor", "Picture Engine"],
        "hdmi_ports": ["HDMI Ports", "HDMI Inputs Total", "HDMI"],
        "usb_ports": ["USB Ports", "USB"],
        "hdmi_version": [],
        "wifi_standard": ["Wi-Fi", "Wireless Type", "WiFi"],
        "bluetooth_version": ["Bluetooth", "Bluetooth Version"],
        "ethernet_lan": ["Ethernet", "Ethernet (LAN)"],
        "speaker_output_watts": ["Sound Output", "Wattage", "Audio Power Output", "Sound"],
        "speaker_configuration": ["Speaker Type", "Sound System", "Sound Type", "Speaker"],
        "dolby_audio": ["Dolby Audio", "Dolby Sound"],
        "voice_assistant": ["Voice Assistant", "Voice Assistants Built-in", "Voice Recognition", "Voice Search"],
        "energy_rating": ["Energy Rating", "Energy Rating (BEE)", "Energy Rating (India)"],
        "power_consumption_w": ["Power Consumption", "Power Consumption (Typ.)", "Power Consumption (Max)"],
        "weight_kg": ["Weight", "Item Weight", "Weight (without Stand)", "Weight without Stand"],
        "dimensions_mm": ["Dimensions", "Product Dimensions", "Dimensions (WxHxD, without Stand)",
                          "Dimensions (WxHxD)", "Dimension without Stand", "Product Dimensions (WxHxD)"],
        "warranty_years": ["Warranty", "Warranty Summary"],
    }

    for field, aliases in alias_map.items():
        for a in aliases:
            if a in raw:
                v = raw[a]
                cleaned = _coerce(field, v)
                if cleaned is not None:
                    out[field] = cleaned
                    break

    return out


def _coerce(field: str, value: str) -> Any:
    if value is None:
        return None
    v = str(value).strip()
    if not v:
        return None

    if field == "screen_size_inches":
        m = re.search(r"(\d+(?:\.\d+)?)\s*(?:inch|inches|\")", v, re.IGNORECASE)
        if m:
            return float(m.group(1))
        m = re.search(r"(\d+(?:\.\d+)?)\s*cm", v, re.IGNORECASE)
        if m:
            return round(float(m.group(1)) / 2.54, 1)
        m = re.search(r"^(\d+(?:\.\d+)?)$", v)
        if m:
            return float(m.group(1))
    if field == "resolution":
        vl = v.lower()
        if "8k" in vl:
            return "8K UHD"
        if "4k" in vl or "3840" in vl:
            return "4K UHD"
        if "full hd" in vl or "1920" in vl:
            return "Full HD"
        return "4K UHD"
    if field == "resolution_pixels":
        m = re.search(r"(\d{3,4})\s*[x×]\s*(\d{3,4})", v)
        if m:
            return f"{m.group(1)}x{m.group(2)}"
        if "4k" in v.lower():
            return "3840x2160"
    if field == "display_type":
        vl = v.lower()
        for kind in ["neo qled", "mini-led", "qled", "oled", "nanocell", "led"]:
            if kind in vl:
                return kind.upper().replace("-LED", "-LED")
        return "LED"
    if field == "operating_system":
        vl = v.lower()
        for label, canonical in [
            ("tizen", "Tizen"), ("webos", "webOS"), ("google tv", "Google TV"),
            ("android tv", "Android TV"), ("fire tv", "Fire TV"),
            ("roku", "Roku TV"), ("vidaa", "VIDAA"), ("patchwall", "PatchWall"),
        ]:
            if label in vl:
                return canonical
        return v.strip()
    if field == "hdmi_version":
        m = re.search(r"hdmi\s*(2\.1|2\.0|1\.4)", v, re.IGNORECASE)
        if m:
            return m.group(1)
        return None
    if field == "refresh_rate_hz":
        m = re.search(r"(\d+)\s*hz", v, re.IGNORECASE)
        if m:
            return int(m.group(1))
    if field == "smart_tv":
        return v.strip().lower() in {"yes", "true", "smart tv"}
    if field == "hdmi_ports" or field == "usb_ports":
        m = re.search(r"(\d+)", v)
        if m:
            return int(m.group(1))
    if field == "wifi_standard":
        vl = v.lower()
        if "802.11ax" in vl or "wifi 6" in vl or "wi-fi 6" in vl:
            return "WiFi 6 (802.11ax)"
        if "802.11ac" in vl or "wifi 5" in vl or "wi-fi 5" in vl:
            return "WiFi 5 (802.11ac)"
        if "802.11n" in vl or "wifi 4" in vl:
            return "WiFi 4 (802.11n)"
        if vl in {"yes", "true"}:
            return "WiFi 5 (802.11ac)"
    if field == "bluetooth_version":
        m = re.search(r"(\d+\.\d+)", v)
        if m:
            return m.group(1)
        if v.strip().lower() == "yes":
            return "5.0"
    if field == "ethernet_lan":
        return v.strip().lower() in {"yes", "true"}
    if field == "speaker_output_watts":
        m = re.search(r"(\d+)\s*w", v, re.IGNORECASE)
        if m:
            return int(m.group(1))
    if field == "dolby_audio":
        return "dolby" in v.lower() and "no" not in v.lower()
    if field == "power_consumption_w":
        m = re.search(r"(\d+)\s*w", v, re.IGNORECASE)
        if m:
            return int(m.group(1))
    if field == "weight_kg":
        m = re.search(r"(\d+(?:\.\d+)?)\s*kg", v, re.IGNORECASE)
        if m:
            return float(m.group(1))
    if field == "dimensions_mm":
        m = re.search(r"(\d+(?:\.\d+)?)\s*[x×]\s*(\d+(?:\.\d+)?)\s*[x×]\s*(\d+(?:\.\d+)?)", v)
        if m:
            return f"{m.group(1)}x{m.group(2)}x{m.group(3)} mm"
    if field == "warranty_years":
        m = re.search(r"(\d+)\s*year", v, re.IGNORECASE)
        if m:
            return int(m.group(1))
        return 1
    return v


def _guess_from_text(field: str, text: str) -> Any | None:
    if not text:
        return None
    t = text.lower()
    if field == "hdmi_version" and "hdmi 2.1" in t:
        return "2.1"
    if field == "wifi_standard":
        if "wi-fi 6" in t or "wifi 6" in t or "802.11ax" in t:
            return "WiFi 6 (802.11ax)"
        if "wi-fi 5" in t or "wifi 5" in t or "802.11ac" in t:
            return "WiFi 5 (802.11ac)"
    if field == "bluetooth_version":
        m = re.search(r"bluetooth\s*(\d+\.\d+)", t)
        if m:
            return m.group(1)
    if field == "energy_rating":
        m = re.search(r"(\d)\s*star", t)
        if m:
            return f"{m.group(1)} Star"
    if field == "launch_year":
        m = re.search(r"(202[3-6])\s*(?:model|edition)", t)
        if m:
            return int(m.group(1))
    return None
