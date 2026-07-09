"""
DoS / 资源耗尽攻击 PoC
"""
import requests
import time
import threading
import sys

TARGET = "http://127.0.0.1:8888"
REQUESTS_PER_BURST = 20

def test_rate_limit():
    """测试速率限制是否有效"""
    print("\n" + "=" * 60)
    print(" DoS 攻击 #1: 速率限制绕过测试")
    print("=" * 60)
    print(f"目标: {TARGET}/ask/?question=test")
    print(f"短时间内发送 {REQUESTS_PER_BURST} 个请求...\n")

    success = 0
    rate_limited = 0
    errors = 0

    for i in range(REQUESTS_PER_BURST):
        try:
            r = requests.get(
                f"{TARGET}/ask/",
                params={"question": f"test{i}"},
                timeout=5
            )
            if r.status_code == 429:
                rate_limited += 1
                print(f"  [{i+1:02d}] 429 Rate Limited ✅ (防御生效)")
            elif r.status_code == 200:
                success += 1
                print(f"  [{i+1:02d}] 200 OK (通过)")
            elif r.status_code == 503:
                errors += 1
                print(f"  [{i+1:02d}] 503 RAG未就绪")
            else:
                errors += 1
                print(f"  [{i+1:02d}] {r.status_code} Unexpected")
        except Exception as e:
            errors += 1
            print(f"  [{i+1:02d}] ERROR: {e}")

    print(f"\n  结果: {success} 成功 / {rate_limited} 被限 / {errors} 错误")

    if rate_limited > 0:
        print("  ✅ 速率限制正常工作")
    else:
        print("  ⚠️  速率限制可能未生效或被绕过！")


def test_large_input():
    """测试大输入 DoS"""
    print("\n" + "=" * 60)
    print(" DoS 攻击 #2: 超大输入攻击")
    print("=" * 60)

    # 10KB input
    large_query = "A" * 10_000
    print(f"  发送 {len(large_query)} 字符的 question...")
    start = time.time()
    try:
        r = requests.get(f"{TARGET}/ask/", params={"question": large_query}, timeout=10)
        elapsed = time.time() - start
        print(f"  HTTP {r.status_code} (耗时 {elapsed:.2f}s)")

        if r.status_code == 422:
            print("  ✅ 输入长度限制生效 (422 — 输入过长)")
        elif r.status_code == 200:
            print("  ⚠️  接受了超长输入！可能导致 token 耗尽")
        else:
            print(f"  ⚠️  非预期状态码: {r.status_code}")
    except requests.Timeout:
        print("  🔴 请求超时 — 可能存在 DoS 风险")
    except Exception as e:
        print(f"  ERROR: {e}")

    # 空输入
    print(f"\n  发送空 question...")
    try:
        r = requests.get(f"{TARGET}/ask/", params={"question": ""}, timeout=10)
        print(f"  HTTP {r.status_code}")
        if r.status_code == 422:
            print("  ✅ 空输入被 min_length=1 拒绝")
        elif r.status_code == 400:
            print("  ✅ 空输入被手动检查拒绝")
        else:
            print("  ⚠️  空输入未被有效拦截")
    except Exception as e:
        print(f"  ERROR: {e}")


def test_concurrent_admin_requests():
    """测试 Admin 端点的并发请求 (如果没有 Rate Limit)"""
    print("\n" + "=" * 60)
    print(" DoS 攻击 #3: Admin 端点并发探测")
    print("=" * 60)

    TARGET_ADMIN = f"{TARGET}/admin/stats"
    results = {"200": 0, "403": 0, "429": 0, "other": 0}
    lock = threading.Lock()

    def make_request(i):
        try:
            r = requests.get(TARGET_ADMIN, timeout=5)
            with lock:
                key = str(r.status_code)
                if key in ("200", "403", "429"):
                    results[key] += 1
                else:
                    results["other"] += 1
        except:
            with lock:
                results["other"] += 1

    threads = []
    print(f"  同时发送 10 个并发 Admin 请求...")
    for i in range(10):
        t = threading.Thread(target=make_request, args=(i,))
        threads.append(t)
        t.start()

    for t in threads:
        t.join(timeout=10)

    print(f"  结果: {results}")
    if results["429"] > 0:
        print("  ✅ Admin 端点限速正常")
    else:
        print("  ⚠️  Admin 端点没有限速保护！可被暴力枚举")


def test_concurrent_ask():
    """测试同时大量请求（并发测试）"""
    print("\n" + "=" * 60)
    print(" DoS 攻击 #4: 并发请求风暴")
    print("=" * 60)

    results_concurrent = {"success": 0, "rate_limited": 0, "error": 0}
    lock = threading.Lock()

    def make_ask_request(i):
        try:
            r = requests.get(
                f"{TARGET}/ask/",
                params={"question": f"concurrent test {i}"},
                timeout=10
            )
            with lock:
                if r.status_code == 200:
                    results_concurrent["success"] += 1
                elif r.status_code == 429:
                    results_concurrent["rate_limited"] += 1
                else:
                    results_concurrent["error"] += 1
        except:
            with lock:
                results_concurrent["error"] += 1

    NUM = 15
    threads = []
    print(f"  同时发送 {NUM} 个请求...")
    start = time.time()
    for i in range(NUM):
        t = threading.Thread(target=make_ask_request, args=(i,))
        threads.append(t)
        t.start()

    for t in threads:
        t.join(timeout=15)

    elapsed = time.time() - start
    print(f"  耗时: {elapsed:.2f}s")
    print(f"  结果: {results_concurrent}")
    if results_concurrent["rate_limited"] > 0:
        print("  ✅ 限速在并发场景下仍有效")
    if results_concurrent["success"] > 10:
        print("  ⚠️  限速可能被并发绕过！(slowapi 计数可能不是原子的)")


if __name__ == "__main__":
    print("=" * 65)
    print(" DoS / 资源耗尽攻击测试套件")
    print("=" * 65)
    print(f"目标: {TARGET}")
    print(f"注意: 这是授权的安全测试\n")

    test_rate_limit()
    test_large_input()
    test_concurrent_admin_requests()
    test_concurrent_ask()

    print(f"\n{'='*65}")
    print(" DoS 防御建议")
    print(f"{'='*65}")
    print("""
  1. 应用层限速 (slowapi) ← 已实施
  2. 反向代理层限速 (nginx rate limiting)
  3. WAF 层限速 (Cloudflare Rate Limiting)
  4. 连接池限制 (uvicorn --limit-concurrency)
  5. 请求体大小限制 (uvicorn --limit-max-requests)
  6. 超时配置 (timeout for all external calls)
  7. 监控告警 (异常流量检测)
""")
