"""
OA 系统连接器：与企业内部 OA 审批 API 对接。
未配置 OA_BASE_URL / OA_API_TOKEN 时返回模拟结果，便于在无 OA 环境下验证流程。
"""
import json
import os
import urllib.error
import urllib.request
from typing import Any, Dict, Optional, Tuple


def _get_oa_config() -> Tuple[Optional[str], Optional[str]]:
    base_url = os.environ.get("OA_BASE_URL", "").rstrip("/")
    token = os.environ.get("OA_API_TOKEN", "")
    return (base_url if base_url else None, token if token else None)


def _request(
    method: str,
    path: str,
    body: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    base_url, token = _get_oa_config()
    if not base_url or not token:
        return {
            "ok": False,
            "error": "OA 未配置",
            "message": "请在 Host 环境配置 OA_BASE_URL 与 OA_API_TOKEN 后重试。当前为模拟模式。",
        }
    url = f"{base_url}{path}"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }
    data = json.dumps(body).encode("utf-8") if body else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return {
            "ok": False,
            "error": f"OA 接口错误 {e.code}",
            "message": e.read().decode("utf-8") if e.fp else str(e),
        }
    except Exception as e:
        return {"ok": False, "error": "OA 请求异常", "message": str(e)}


def submit_approval(
    approval_type: str,
    params: Dict[str, Any],
) -> Dict[str, Any]:
    """
    发起审批。
    approval_type: leave | expense | purchase
    params: 类型对应参数，如 {"reason": "...", "days": 3}
    """
    base_url, token = _get_oa_config()
    if not base_url or not token:
        # 模拟成功，便于联调
        return {
            "ok": True,
            "approval_id": f"mock-{approval_type}-{hash(json.dumps(params, sort_keys=True)) % 100000}",
            "message": "审批已提交（模拟）。配置 OA_BASE_URL 与 OA_API_TOKEN 后将对接真实 OA。",
            "type": approval_type,
            "params": params,
        }
    return _request("POST", "/api/approval/submit", body={"type": approval_type, "params": params})


def query_approval_status(approval_id: Optional[str] = None) -> Dict[str, Any]:
    """
    查询审批状态。
    approval_id: 可选，不传则返回当前用户近期审批列表。
    """
    base_url, token = _get_oa_config()
    if not base_url or not token:
        return {
            "ok": True,
            "list": [
                {"id": "mock-1", "type": "leave", "status": "approved", "summary": "请假 3 天（模拟）"},
            ],
            "message": "当前为模拟数据。配置 OA 后可查询真实审批。",
        }
    path = f"/api/approval/query?id={approval_id}" if approval_id else "/api/approval/list"
    return _request("GET", path)
