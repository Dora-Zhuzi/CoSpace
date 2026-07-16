"""新工作流端到端冒烟测试：素材库 → 共创讨论 → 写作方案 → 结构树 → 片段挂载 → 文章生成。

用法：先用临时库启动 uvicorn（见下方命令），再 `python smoke_test_new.py`。
"""
import io
import json
import time
import uuid
import urllib.request
import urllib.error

BASE = "http://localhost:8003"


def req(method, path, token=None, json_body=None, multipart=None):
    url = BASE + path
    headers = {}
    data = None
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if json_body is not None:
        data = json.dumps(json_body).encode()
        headers["Content-Type"] = "application/json"
    if multipart is not None:
        boundary = "----smoke" + uuid.uuid4().hex
        fname, content = multipart
        body = io.BytesIO()
        body.write(f"--{boundary}\r\n".encode())
        body.write(f'Content-Disposition: form-data; name="file"; filename="{fname}"\r\n'.encode())
        body.write(b"Content-Type: text/plain\r\n\r\n")
        body.write(content)
        body.write(f"\r\n--{boundary}--\r\n".encode())
        data = body.getvalue()
        headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
    r = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r) as resp:
            raw = resp.read()
            ct = resp.headers.get("Content-Type", "")
            return resp.status, (json.loads(raw) if raw and ct.startswith("application/json") else raw)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def wait(check, desc, timeout=60):
    start = time.time()
    val = None
    while time.time() - start < timeout:
        ok, val = check()
        if ok:
            return val
        time.sleep(1)
    raise TimeoutError(f"超时：{desc}（最后值={val}）")


def find_leaf(node):
    if not node.get("children"):
        return node
    return find_leaf(node["children"][0])


def main():
    s, h = req("GET", "/health")
    assert s == 200, h
    print(f"[health] {h}")

    email = f"u{uuid.uuid4().hex[:8]}@test.com"
    _, r = req("POST", "/auth/register", json_body={"email": email, "password": "pw123456"})
    token = r["access_token"]
    print(f"[auth] 注册 {email}")

    _, folder = req("POST", "/materials/folders", token=token, json_body={"name": "ML资料"})
    fid = folder["id"]
    sample = (
        "机器学习概述\n\n机器学习是人工智能的分支，让计算机从数据中学习规律。\n\n"
        "监督学习\n\n监督学习用带标签数据训练模型，常见于分类和回归。\n\n"
        "模型评估\n\n常用准确率、召回率、F1 等指标衡量表现。"
    )
    req("POST", f"/materials/folders/{fid}/upload", token=token, multipart=("ml.txt", sample.encode()))

    def indexed():
        _, d = req("GET", f"/materials/folders/{fid}", token=token)
        mats = d.get("materials", [])
        if any(m["status"] == "index_failed" for m in mats):
            raise RuntimeError(f"入库失败 {mats}")
        return bool(mats) and all(m["status"] == "indexed" for m in mats), mats
    wait(indexed, "素材入库")
    print("[index] 素材已入库")

    _, proj = req("POST", "/projects", token=token, json_body={"name": "我的文章", "folder_id": fid})
    pid = proj["id"]
    print(f"[project] 创建 {pid}")

    # 共创讨论
    s, conv = req("POST", f"/projects/{pid}/conversations", token=token, json_body={})
    assert s == 201, conv
    cid = conv["id"]
    assert conv["messages"] and conv["messages"][0]["role"] == "assistant", conv
    print(f"[discuss] 固定开场: {conv['messages'][0]['content'][:30]}…")

    s, reply = req("POST", f"/projects/{pid}/conversations/{cid}/messages", token=token,
                   json_body={"content": "我想写给初学者，重点讲清楚监督学习和模型评估。"})
    assert s == 201, reply
    print(f"[discuss] 回复: {reply['content'][:40]}…")

    # 草稿便签（按讨论归属）
    s, card = req("POST", f"/projects/{pid}/cards", token=token,
                  json_body={"conversation_id": cid, "type": "plan", "title": "问题驱动展开",
                             "content": "面向初学者，先讲监督学习再讲模型评估，配实例。"})
    assert s == 201, card
    req("POST", f"/projects/{pid}/cards", token=token,
        json_body={"conversation_id": cid, "type": "case", "content": "用垃圾邮件分类作为监督学习的例子。"})
    _, cards = req("GET", f"/projects/{pid}/cards?conversation_id={cid}", token=token)
    print(f"[cards] 该讨论已沉淀 {len(cards)} 张便签")

    # 把观点卡片保存进素材库
    vp = next((c for c in cards if c["type"] == "viewpoint"), None)
    assert vp, "缺少默认观点卡片"
    req("PATCH", f"/projects/{pid}/cards/{vp['id']}", token=token,
        json_body={"content": "核心观点：从读者价值出发。"})
    s, sm = req("POST", f"/projects/{pid}/cards/{vp['id']}/save-material", token=token)
    assert s == 201, sm
    _, folder = req("GET", f"/materials/folders/{fid}", token=token)
    names = [m["filename"] for m in folder["materials"]]
    assert any(n.endswith("-观点.md") for n in names), names
    print(f"[save-material] 素材库现有文件：{names}")

    # 写作方案（基于该讨论的便签）
    s, plan = req("POST", f"/projects/{pid}/plan", token=token, json_body={"conversation_id": cid})
    assert s == 200 and plan.get("id") and plan.get("content"), plan
    plan_id = plan["id"]
    _, plist = req("GET", f"/projects/{pid}/plans", token=token)
    assert any(p["id"] == plan_id for p in plist), plist
    print(f"[plan] 生成即保存「{plan['name']}」{len(plan['content'])} 字；方案列表 {len(plist)} 份")

    # 结构树
    s, tree = req("POST", f"/projects/{pid}/trees", token=token, json_body={"plan_id": plan_id})
    assert s == 201, tree
    tid = tree["id"]

    def tree_ready():
        _, ts = req("GET", f"/projects/{pid}/trees", token=token)
        t = next((x for x in ts if x["id"] == tid), None)
        if t and t["status"] == "failed":
            raise RuntimeError("结构树生成失败")
        return (t is not None and t["status"] == "ready"), (t["status"] if t else "?")
    wait(tree_ready, "结构树生成+自动挂载", timeout=120)

    _, ts = req("GET", f"/projects/{pid}/trees", token=token)
    tree = next(x for x in ts if x["id"] == tid)
    nodes = tree["nodes"]

    def count_mounts(n):
        c = len(n.get("chunk_ids") or [])
        for ch in n.get("children") or []:
            c += count_mounts(ch)
        return c
    print(f"[tree] 根='{nodes['label']}'，章节数={len(nodes['children'])}，自动挂载片段数={count_mounts(nodes)}")

    # 验证手动调整挂载仍可保存：在第一个叶子上追加一个片段
    _, chunks = req("GET", f"/projects/{pid}/chunks", token=token)
    assert chunks, "无可挂载片段"
    leaf = find_leaf(nodes)
    leaf["chunk_ids"] = list({*(leaf.get("chunk_ids") or []), chunks[0]["chunk_id"]})
    s, updated = req("PATCH", f"/projects/{pid}/trees/{tid}", token=token, json_body={"nodes": nodes})
    assert s == 200, updated
    print(f"[mount] 手动调整已保存到节点 '{leaf['label']}'")

    # 文章生成
    s, doc = req("POST", f"/projects/{pid}/trees/{tid}/documents", token=token)
    assert s == 201, doc
    did = doc["id"]

    def done():
        _, ds = req("GET", f"/projects/{pid}/trees/{tid}/documents", token=token)
        d = next((x for x in ds if x["id"] == did), None)
        if d and d["status"] == "failed":
            raise RuntimeError("文章生成失败")
        return (d and d["status"] == "done"), (d["status"] if d else "?")
    wait(done, "文章生成")

    # 生成即保存为一份文章
    _, alist = req("GET", f"/projects/{pid}/articles", token=token)
    assert alist, "未生成文章"
    latest = alist[-1]
    assert latest["content"].startswith("# "), latest["content"][:80]
    print(f"[article] 生成即保存「{latest['name']}」{len(latest['content'])} 字；文章列表 {len(alist)} 份")
    print("\n✅ 新流程全程通过")


if __name__ == "__main__":
    main()
