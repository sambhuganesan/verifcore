import argparse
import random

def write_record(
    f,
    suite,
    test_name,
    seed,
    worker,
    cycles,
    expected_cycles,
    utilization,
    status,
    failure_type=None,
    assertion_name=None,
    artifact_path=None,
):
    f.write(f"[RUN] suite={suite} test={test_name} seed={seed} worker={worker}\n")
    f.write(
        f"[METRIC] cycles={cycles} expected_cycles={expected_cycles} "
        f"utilization={utilization}\n"
    )

    if status == "PASS":
        f.write("[PASS]\n")
    else:
        f.write(
            f"[FAIL] type={failure_type} "
            f"assertion={assertion_name} "
            f"artifact={artifact_path}\n"
        )

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--num-tests", type=int, default=1)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--inject-regressions", action="store_true")
    
    args = parser.parse_args()
    random.seed(args.seed)

    suites = ["dma", "systolic_array", "cache", "noc", "decoder"]
    tests = [
        "aligned_burst",
        "backpressure",
        "randomized_smoke",
        "reset_recovery",
        "protocol_stress",
    ]
    assertions = [
        "valid_ready_protocol",
        "fifo_no_overflow",
        "reset_clears_state",
        "packet_ordering",
    ]
    with open(args.out, "w") as f:
        for i in range(args.num_tests):
            suite = suites[i % len(suites)]
            test_name = tests[i % len(tests)] + f"_{i}"
            seed = 1000 + i
            worker = f"worker-{i % 8}"

            expected_cycles = 700 + (i % 20) * 25
            cycles = expected_cycles + random.randint(-50, 80)
            variant_i = i + args.seed
            if args.inject_regressions and variant_i % 19 == 0:
                cycles = int(cycles * 1.30)
            utilization = round(random.uniform(0.60, 0.95), 2)

            baseline_fail = i % 13 == 0
            is_fail = baseline_fail

            if args.inject_regressions:
                if variant_i % 26 == 0:
                    is_fail = False
                if variant_i % 17 == 0:
                    is_fail = True
                if variant_i % 23 == 0:
                    is_fail = True

            if is_fail:
                status = "FAIL"

                if args.inject_regressions and variant_i % 23 == 0:
                    failure_type = "INFRA_FAILURE"
                    assertion_name = "sim_timeout"
                else:
                    failure_type = "ASSERTION_FAILED"
                    assertion_name = assertions[i % len(assertions)]

                artifact_path = f"waves/{suite}_{test_name}_seed{seed}.vcd"
            else:
                status = "PASS"
                failure_type = None
                assertion_name = None
                artifact_path = None

            write_record(
                f,
                suite,
                test_name,
                seed,
                worker,
                cycles,
                expected_cycles,
                utilization,
                status,
                failure_type,
                assertion_name,
                artifact_path,
            )

            f.write("\n")

if __name__ == "__main__":
    main()
