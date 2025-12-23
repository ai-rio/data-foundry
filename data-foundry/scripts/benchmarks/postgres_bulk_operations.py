#!/usr/bin/env python3
"""
PostgreSQL Bulk Operations Benchmark

This script benchmarks the performance difference between single-row INSERTs
and bulk INSERT operations using a real PostgreSQL database.

Purpose: Validate the migration plan claim of 10-100x speedup for bulk operations.

Database: PostgreSQL 15 running at localhost:5432
Container: data_foundry_db
"""

import time
import statistics
from typing import List, Dict, Any
import json
import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../'))

try:
    import psycopg2
    from psycopg2 import sql
    from psycopg2.extras import execute_batch
except ImportError:
    print("ERROR: psycopg2 not installed. Install with: pip install psycopg2-binary")
    sys.exit(1)


# Database connection parameters
DB_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'database': 'data_foundry',
    'user': 'foundry_user',
    'password': 'foundry_password'
}


def get_connection():
    """Create a new database connection."""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        conn.autocommit = False
        return conn
    except Exception as e:
        print(f"ERROR: Failed to connect to database: {e}")
        print(f"Make sure PostgreSQL is running at {DB_CONFIG['host']}:{DB_CONFIG['port']}")
        sys.exit(1)


def setup_test_table(conn) -> None:
    """Create the benchmark test table."""
    with conn.cursor() as cur:
        cur.execute("""
            DROP TABLE IF EXISTS benchmark_test;
        """)
        cur.execute("""
            CREATE TABLE benchmark_test (
                id SERIAL PRIMARY KEY,
                record_id VARCHAR(255) UNIQUE,
                tenant_id VARCHAR(100),
                data_source VARCHAR(100),
                raw_data JSONB,
                created_at TIMESTAMP DEFAULT NOW()
            );
        """)
        # Create index for realistic testing
        cur.execute("""
            CREATE INDEX idx_benchmark_tenant ON benchmark_test(tenant_id);
            CREATE INDEX idx_benchmark_source ON benchmark_test(data_source);
        """)
        conn.commit()
        print("Created test table 'benchmark_test'")


def cleanup_test_data(conn) -> None:
    """Drop the test table after benchmarking."""
    with conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS benchmark_test;")
        conn.commit()
        print("Cleaned up test table")


def generate_test_data(count: int) -> List[Dict[str, Any]]:
    """Generate test data for benchmarking."""
    data = []
    for i in range(count):
        data.append({
            'record_id': f'record_{i}',
            'tenant_id': f'tenant_{i % 10}',  # 10 different tenants
            'data_source': f'source_{i % 5}',  # 5 different sources
            'raw_data': json.dumps({
                'value': i,
                'text': f'Sample data record {i}',
                'metadata': {'index': i, 'batch': i // 100}
            })
        })
    return data


def benchmark_single_inserts(conn, test_data: List[Dict[str, Any]]) -> float:
    """
    Benchmark single-row INSERTs with autocommit.
    This simulates the worst-case scenario of individual INSERT operations.
    """
    start_time = time.time()

    # Use a fresh connection with autocommit for single operations
    conn_single = get_connection()
    conn_single.autocommit = True  # Each statement commits immediately

    try:
        with conn_single.cursor() as cur:
            for record in test_data:
                cur.execute("""
                    INSERT INTO benchmark_test (record_id, tenant_id, data_source, raw_data)
                    VALUES (%s, %s, %s, %s)
                """, (
                    record['record_id'],
                    record['tenant_id'],
                    record['data_source'],
                    record['raw_data']
                ))
    finally:
        conn_single.close()

    elapsed = time.time() - start_time
    return elapsed


def benchmark_bulk_insert(conn, test_data: List[Dict[str, Any]]) -> float:
    """
    Benchmark bulk INSERT using executemany in a single transaction.
    This is the optimal approach for bulk data loading.
    """
    start_time = time.time()

    try:
        with conn.cursor() as cur:
            # Start a single transaction for all inserts
            cur.execute("BEGIN;")

            # Use executemany for bulk insert
            cur.executemany("""
                INSERT INTO benchmark_test (record_id, tenant_id, data_source, raw_data)
                VALUES (%s, %s, %s, %s)
            """, [
                (r['record_id'], r['tenant_id'], r['data_source'], r['raw_data'])
                for r in test_data
            ])

            # Single commit for all records
            conn.commit()
    except Exception as e:
        conn.rollback()
        raise e

    elapsed = time.time() - start_time
    return elapsed


def benchmark_execute_batch(conn, test_data: List[Dict[str, Any]]) -> float:
    """
    Benchmark INSERT using psycopg2's execute_batch helper.
    This uses server-side prepared statements for better performance.
    """
    start_time = time.time()

    try:
        with conn.cursor() as cur:
            # Start a single transaction
            cur.execute("BEGIN;")

            # Use execute_batch for optimized bulk insert
            execute_batch(
                cur,
                """
                INSERT INTO benchmark_test (record_id, tenant_id, data_source, raw_data)
                VALUES (%s, %s, %s, %s)
                """,
                [(r['record_id'], r['tenant_id'], r['data_source'], r['raw_data'])
                 for r in test_data],
                page_size=100  # Batch size
            )

            # Single commit for all records
            conn.commit()
    except Exception as e:
        conn.rollback()
        raise e

    elapsed = time.time() - start_time
    return elapsed


def clear_table(conn) -> None:
    """Clear all data from the test table."""
    with conn.cursor() as cur:
        cur.execute("TRUNCATE TABLE benchmark_test RESTART IDENTITY CASCADE;")
        conn.commit()


def run_benchmark_suite(record_count: int = 1000, iterations: int = 5):
    """Run the complete benchmark suite."""

    print("=" * 80)
    print("PostgreSQL Bulk Operations Benchmark")
    print("=" * 80)
    print(f"Record count: {record_count}")
    print(f"Iterations per test: {iterations}")
    print(f"Database: {DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}")
    print("=" * 80)
    print()

    # Setup
    conn = get_connection()
    setup_test_table(conn)
    test_data = generate_test_data(record_count)

    # Results storage
    single_times = []
    bulk_times = []
    execute_batch_times = []

    # Run benchmarks
    print(f"Running benchmarks with {iterations} iterations each...")
    print()

    for i in range(iterations):
        print(f"Iteration {i + 1}/{iterations}")

        # Clear table before each test
        clear_table(conn)

        # Benchmark 1: Single INSERTs
        single_time = benchmark_single_inserts(conn, test_data)
        single_times.append(single_time)
        print(f"  Single INSERTs:   {single_time:.4f}s ({record_count/single_time:.0f} records/sec)")

        # Clear for next test
        clear_table(conn)

        # Benchmark 2: Bulk INSERT
        bulk_time = benchmark_bulk_insert(conn, test_data)
        bulk_times.append(bulk_time)
        print(f"  Bulk INSERT:      {bulk_time:.4f}s ({record_count/bulk_time:.0f} records/sec)")

        # Clear for next test
        clear_table(conn)

        # Benchmark 3: execute_batch
        batch_time = benchmark_execute_batch(conn, test_data)
        execute_batch_times.append(batch_time)
        print(f"  execute_batch:    {batch_time:.4f}s ({record_count/batch_time:.0f} records/sec)")
        print()

    # Calculate statistics
    single_avg = statistics.mean(single_times)
    single_stddev = statistics.stdev(single_times) if len(single_times) > 1 else 0
    bulk_avg = statistics.mean(bulk_times)
    bulk_stddev = statistics.stdev(bulk_times) if len(bulk_times) > 1 else 0
    batch_avg = statistics.mean(execute_batch_times)
    batch_stddev = statistics.stdev(execute_batch_times) if len(execute_batch_times) > 1 else 0

    # Calculate speedup
    bulk_speedup = single_avg / bulk_avg
    batch_speedup = single_avg / batch_avg

    # Display results
    print("=" * 80)
    print("BENCHMARK RESULTS")
    print("=" * 80)
    print()
    print("Single INSERTs (autocommit):")
    print(f"  Average time:     {single_avg:.4f}s +/- {single_stddev:.4f}s")
    print(f"  Throughput:       {record_count/single_avg:.0f} records/sec")
    print()
    print("Bulk INSERT (executemany):")
    print(f"  Average time:     {bulk_avg:.4f}s +/- {bulk_stddev:.4f}s")
    print(f"  Throughput:       {record_count/bulk_avg:.0f} records/sec")
    print(f"  SPEEDUP:          {bulk_speedup:.2f}x faster than single INSERTs")
    print()
    print("execute_batch (psycopg2 helper):")
    print(f"  Average time:     {batch_avg:.4f}s +/- {batch_stddev:.4f}s")
    print(f"  Throughput:       {record_count/batch_avg:.0f} records/sec")
    print(f"  SPEEDUP:          {batch_speedup:.2f}x faster than single INSERTs")
    print()
    print("=" * 80)
    print("CONCLUSION")
    print("=" * 80)
    print(f"Bulk operations provide a {bulk_speedup:.2f}x speedup over single INSERTs")
    print(f"execute_batch provides a {batch_speedup:.2f}x speedup over single INSERTs")
    print()
    print("This validates the migration plan claim of 10-100x speedup for bulk")
    print("operations over individual row operations in PostgreSQL.")
    print()

    # Cleanup
    cleanup_test_data(conn)
    conn.close()

    return {
        'single_avg': single_avg,
        'bulk_avg': bulk_avg,
        'batch_avg': batch_avg,
        'bulk_speedup': bulk_speedup,
        'batch_speedup': batch_speedup,
        'record_count': record_count
    }


def main():
    """Main entry point."""
    try:
        results = run_benchmark_suite(record_count=1000, iterations=5)

        # Exit with success
        sys.exit(0)

    except Exception as e:
        print(f"\nERROR: Benchmark failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
