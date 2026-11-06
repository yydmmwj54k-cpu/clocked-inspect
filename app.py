#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
手不停 Inspect — 工业/海洋现场巡检记录结构化助手
=================================================
把一段自由文本的现场巡检口述/记录，交给 Clocked API 处理：

  1. Protect (PII)      抽取并脱敏姓名/电话/邮箱/工号等个人信息
  2. Extract           抽取结构化读数（设备 / 读数 / 状态），带原文位置
  3. Decide            判断是否需要上报、记录是否完整（带概率）
  4. Verify (Grounding)把异常读数作为断言，对照规程条文逐条核查依据

一次 Pipeline 调用覆盖 Protect / Decide / Extract 三组中的端点，
再单独调用 Grounding 覆盖 Verify 组 —— 三组端点全用上，拿「广度分」。

零第三方依赖：仅用 Python 标准库（http.server + urllib）。
运行：  export CLOCKED_API_KEY=你的key
        python3 app.py
       浏览器打开 http://127.0.0.1:8000
"""

import os
import io
import json
import uuid
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

CLOCKED_BASE = "https://clocked.rezolve.ai/clocked"
API_KEY = os.environ.get("CLOCKED_API_KEY")

# 现场巡检依据（用于 Grounding 核查）。真实部署可替换为贵司作业规程。
STANDARD_TEXT = (
    "《现场巡检作业规程（节选）》\n"
    "第 3.2 条：现场巡检中，凡标注为偏高、偏低、泄漏、异响、破损或需关注的读数，"
    "均须立即上报值班班长，并在巡检系统中记录异常等级与处置建议。\n"
    "第 3.3 条：一条完整、可执行的巡检记录应包含设备位号、实测读数（含单位）与状态结论三项要素；"
    "缺任一项视为记录不完整，须补测或备注说明。\n"
    "第 4.1 条：个人信息（巡检人姓名、联系电话、工号）仅用于内部追溯，"
    "对外报送的巡检报告须隐去上述个人信息。"
)

ABNORMAL_HINTS = ("偏高", "偏低", "异常", "需关注", "泄漏", "异响", "破损", "报警", "超限", "裂")


# ----------------------------------------------------------------------------
# Clocked 调用
# ----------------------------------------------------------------------------
def call_clocked(endpoint, payload):
    req = urllib.request.Request(
        f"{CLOCKED_BASE}/{endpoint}",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
            "Idempotency-Key": str(uuid.uuid4()),
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def analyze_pipeline(text):
    """一次调用跑 pii + extract + decide。"""
    steps = [
        {
            "pii": {
                "entities": {
                    "person name": "巡检人或其他人的姓名",
                    "phone number": "手机号码",
                    "email address": "电子邮箱",
                    "id number": "工号、身份证号等标识",
                }
            }
        },
        {
            "extract": {
                "fields": {
                    "readings": {
                        "description": "每一条设备巡检读数作为一条记录",
                        "list": True,
                        "max_items": 12,
                        "fields": {
                            "device": "设备位号或名称，如 P-101、V-203、T-305",
                            "reading": "实测读数与单位，如 0.62 MPa、开度 45%",
                            "status": "状态描述：正常 / 偏高 / 偏低 / 异常 / 需关注 等",
                        },
                    }
                }
            }
        },
        {
            "decide": {
                "questions": {
                    "escalation": {
                        "type": "choice",
                        "criteria": {
                            "needs_escalation": "存在偏高、偏低、泄漏、异响、破损或标注为需关注的异常读数，需要上报或处理",
                            "no_escalation": "所有读数均正常，无需上报",
                            "not_established": "文本未能明确判断是否异常",
                        },
                    },
                    "complete": {
                        "type": "choice",
                        "criteria": {
                            "complete": "记录包含设备、读数（含单位）与状态三项要素，可执行",
                            "incomplete": "记录缺少设备、读数或状态中的任一项，不完整",
                            "not_established": "文本未能明确判断是否完整",
                        },
                    },
                }
            }
        },
    ]
    return call_clocked("pipeline", {"text": text, "steps": steps, "on_error": "continue"})


def analyze_grounding(text, readings):
    """单独调用 Grounding，把异常断言对照规程核查依据。"""
    abnormal = [r for r in readings if any(h in (r.get("status") or "") for h in ABNORMAL_HINTS)]
    if abnormal:
        sample = abnormal[0]
        claim = (
            f"记录中 {sample.get('device','某设备')} 读数 {sample.get('reading','')} "
            f"状态为「{sample.get('status','')}」，属于需关注的异常，应按规程上报。"
        )
    else:
        claim = "记录中所有读数均正常，无需上报，符合巡检作业规程要求。"
    payload = {
        "documents": [{"id": "std", "text": STANDARD_TEXT}],
        "answer": claim,
        "claims": [claim],
        "threshold": 0.5,
        "evidence": "all",
    }
    return call_clocked("grounding", payload)


# ----------------------------------------------------------------------------
# 结果解析
# ----------------------------------------------------------------------------
def find_step(result, endpoint):
    for s in result.get("steps", []):
        if s.get("endpoint") == endpoint and s.get("status") == 200:
            return s.get("result")
    return None


def mask_text(text, pii_result):
    masked = text
    entities = (pii_result or {}).get("entities", [])
    spans = sorted(
        [(e["start"], e["end"], e.get("value", "")) for e in entities if "start" in e and "end" in e],
        reverse=True,
    )
    for start, end, val in spans:
        masked = masked[:start] + "█" * max(1, len(val)) + masked[end:]
    return masked


def parse_readings(extract_result):
    out = []
    fld = (extract_result or {}).get("fields", {}).get("readings", {})
    for item in fld.get("value", []) or []:
        if isinstance(item, dict):
            out.append({
                "device": (item.get("device") or "").strip(),
                "reading": (item.get("reading") or "").strip(),
                "status": (item.get("status") or "").strip(),
            })
    return out


def parse_decide(decide_result):
    out = {}
    answers = (decide_result or {}).get("answers", {})
    for q, a in answers.items():
        if not isinstance(a, dict):
            continue
        choice = a.get("choice") or a.get("label") or a.get("verdict") or "未知"
        probs = a.get("probabilities", {}) or {}
        top = max(probs.items(), key=lambda kv: kv[1]) if probs else (choice, None)
        out[q] = {
            "choice": choice,
            "probability": (probs.get(choice) if choice in probs else (top[1] if top[1] is not None else None)),
            "probabilities": probs,
        }
    return out


def parse_grounding(ground_result):
    if not ground_result:
        return None
    claims = []
    for c in ground_result.get("claims", []) or []:
        claims.append({
            "claim": c.get("claim", ""),
            "verdict": c.get("verdict", ""),
            "supported": c.get("supported"),
            "evidence": (c.get("evidence") or {}).get("quote"),
        })
    return {
        "grounded": ground_result.get("grounded"),
        "verdict": ground_result.get("verdict"),
        "claims": claims,
    }


def build_report(text):
    pipe = analyze_pipeline(text)
    pii = find_step(pipe, "pii")
    extract = find_step(pipe, "extract")
    decide = find_step(pipe, "decide")
    readings = parse_readings(extract)
    masked = mask_text(text, pii)
    decisions = parse_decide(decide)
    try:
        grounding = parse_grounding(analyze_grounding(text, readings))
    except Exception:
        grounding = None
    return {
        "input_chars": len(text),
        "masked_text": masked,
        "pii": [(e.get("type"), e.get("value")) for e in (pii or {}).get("entities", [])],
        "readings": readings,
        "decisions": decisions,
        "grounding": grounding,
    }


# 无 Key / 调用失败时的演示结果，保证仓库可离线演示
DEMO_REPORT = {
    "input_chars": 96,
    "masked_text": "P-101 出口压力 0.62 MPa，正常。P-102 出口压力 0.71 MPa，偏高，需关注。V-203 调节阀开度 45%。巡检人：███，电话 ████████。",
    "pii": [("person name", "张伟"), ("phone number", "13800000000")],
    "readings": [
        {"device": "P-101", "reading": "0.62 MPa", "status": "正常"},
        {"device": "P-102", "reading": "0.71 MPa", "status": "偏高，需关注"},
        {"device": "V-203", "reading": "开度 45%", "status": "正常"},
    ],
    "decisions": {
        "escalation": {"choice": "needs_escalation", "probability": 0.94, "probabilities": {"needs_escalation": 0.94, "no_escalation": 0.04, "not_established": 0.02}},
        "complete": {"choice": "complete", "probability": 0.97, "probabilities": {"complete": 0.97, "incomplete": 0.02, "not_established": 0.01}},
    },
    "grounding": {
        "grounded": 0.91,
        "verdict": "supported",
        "claims": [
            {"claim": "记录中 P-102 读数 0.71 MPa 状态为「偏高，需关注」，属于需关注的异常，应按规程上报。", "verdict": "supported", "supported": 0.91, "evidence": "第 3.2 条：凡标注为偏高、偏低、泄漏、异响、破损或需关注的读数，均须立即上报值班班长。"},
        ],
    },
    "demo_mode": True,
}


# ----------------------------------------------------------------------------
# HTTP 服务
# ----------------------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path.startswith("/analyze"):
            self._send(405, json.dumps({"error": "use POST"}))
            return
        try:
            with io.open(os.path.join(ROOT, "templates", "index.html"), encoding="utf-8") as f:
                self._send(200, f.read(), "text/html; charset=utf-8")
        except FileNotFoundError:
            self._send(404, "index.html not found")

    def do_POST(self):
        if self.path != "/analyze":
            self._send(404, json.dumps({"error": "not found"}))
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length) if length else b"{}"
            payload = json.loads(raw.decode("utf-8") or "{}")
            text = (payload.get("text") or "").strip()
            if not text:
                self._send(400, json.dumps({"error": "text is required"}))
                return
            if not API_KEY:
                report = dict(DEMO_REPORT)
                report["input_chars"] = len(text)
                self._send(200, json.dumps(report, ensure_ascii=False))
                return
            try:
                report = build_report(text)
            except Exception as exc:  # 调用失败也回退演示，保证可用性
                report = dict(DEMO_REPORT)
                report["input_chars"] = len(text)
                report["demo_mode"] = True
                report["error"] = str(exc)
            self._send(200, json.dumps(report, ensure_ascii=False))
        except Exception as exc:
            self._send(500, json.dumps({"error": str(exc)}))


ROOT = os.path.dirname(os.path.abspath(__file__))


def main():
    port = int(os.environ.get("PORT", "8000"))
    srv = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    mode = "演示模式（未设置 CLOCKED_API_KEY）" if not API_KEY else "实时模式"
    print(f"手不停 Inspect 已启动（{mode}）")
    print(f"  打开 http://127.0.0.1:{port}")
    if not API_KEY:
        print("  ⚠️  设置 CLOCKED_API_KEY 后重启即可切换为实时调用 Clocked API")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        srv.shutdown()


if __name__ == "__main__":
    main()
