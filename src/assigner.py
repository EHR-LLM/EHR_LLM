import datetime
import json
import os
import random
import threading
import time
from typing import Dict, List, Union, Optional
from typing import Tuple, Callable, Iterator
import contextlib
import sys
from tqdm.contrib import DummyTqdmFile

import yaml
from tqdm import tqdm

from src.client.task import TaskError
from .client import TaskClient, AgentClient
from .configs import ConfigLoader
from .typings import AssignmentConfig, SampleIndex, TaskOutput, TaskClientOutput
from .utils import ColorMessage
from .utils import Graph, MaxFlow
from time import sleep
import contextlib
import sys
from tqdm import tqdm
from tqdm.contrib import DummyTqdmFile

@contextlib.contextmanager
def std_out_err_redirect_tqdm():
    orig_out_err = sys.stdout, sys.stderr
    try:
        sys.stdout, sys.stderr = map(DummyTqdmFile, orig_out_err)
        yield orig_out_err[0]
    # Relay exceptions
    except Exception as exc:
        raise exc
    # Always restore sys.stdout/err if necessary
    finally:
        sys.stdout, sys.stderr = orig_out_err

class Assigner:
    def __init__(self, config: AssignmentConfig, auto_retry: bool = True,
                 num_replicates: int = 3, model_isolated: bool = True,
                 cross_model_fallback: bool = False) -> None:
        """
        Logic:
            1. Check if output folder exists (resume or create)
            2. Walk through all the folders in output folder, and remove the finished samples
            3. Create agents
            
        Parameters:
            num_replicates: Number of times to run each model (default: 3)
            model_isolated: Run each model completely before next (default: True)
            cross_model_fallback: Allow fallback to other models on failure (default: False)
        """
        self.auto_retry = auto_retry
        self.num_replicates = num_replicates
        self.model_isolated = model_isolated
        self.cross_model_fallback = cross_model_fallback
        self.tqdm_ordered_by_agent: Dict[str, tqdm] = {}
        self.overall_tqdm: Optional[tqdm] = None
        self.config = config
        # Deep copy the concurrency config to track available workers
        self.free_worker = config.concurrency.copy(deep=True)
        # Ensure task dict exists and has proper values
        if not hasattr(self.free_worker, 'task') or self.free_worker.task is None:
            self.free_worker.task = {}
        if not hasattr(self.free_worker, 'agent') or self.free_worker.agent is None:
            self.free_worker.agent = {}
        self.agents: Dict[str, AgentClient] = {}
        self.tasks: Dict[str, TaskClient] = {}
        self.task_indices: Dict[str, List[SampleIndex]] = {}
        self.task_worker_fail_count: Dict[str, int] = {}
        self.assignment_lock = threading.Lock()
        self.remaining_tasks: Dict[
            str, Dict[str, List[SampleIndex]]
        ] = {}  # {agent: {task: [index]}}
        # Track which samples have been started per (agent, task, replicate)
        self.started_samples: Dict[Tuple[str, str, int], set] = {}
        # NEW: Per-replicate isolated completion buckets - no cross-replicate mixing
        # Structure: {agent: {task: {replicate: [completion_data]}}}
        # Each replicate has its own dedicated bucket
        self.completions: Dict[
            str, Dict[str, Dict[int, List]]
        ] = {}
        # NEW: Track completed indices per replicate for idempotency
        # Structure: {agent: {task: {replicate: set()}}}
        self.completed_indices: Dict[
            str, Dict[str, Dict[int, set]]
        ] = {}
        # NEW: Track if overall has been triggered per replicate (one-shot)
        # Structure: {agent: {task: {replicate: bool}}}
        self.overall_triggered: Dict[
            str, Dict[str, Dict[int, bool]]
        ] = {}
        self.finished_count = 0
        self.started_count = 0
        self.running_count = 0

        # Step 1. Check if output folder exists (resume or create)

        if not os.path.exists(self.config.output):
            os.makedirs(self.config.output)
            # Write config file
            with open(os.path.join(self.config.output, "config.yaml"), "w") as f:
                f.write(yaml.dump(self.config.dict()))

        # Step 2. Initialize task clients and remaining tasks (no skip logic for replicates)
        # Each replicate runs independently - no deduplication across replicates

        for assignment in self.config.assignments:
            agent = assignment.agent
            task = assignment.task
            
            # Initialize agent and task if needed
            if task not in self.tasks:
                print(ColorMessage.green(f"creating {task} client..."))
                self.tasks[task] = self.config.definition.task[task].create()
                self.task_indices[task] = self.tasks[task].get_indices()
            
            if agent not in self.remaining_tasks:
                self.remaining_tasks[agent] = {}
            if task not in self.remaining_tasks[agent]:
                self.remaining_tasks[agent][task] = []
            
            # Add all samples - replicates run independently
            self.remaining_tasks[agent][task] = self.task_indices[task].copy()

        # Count total samples (including all replicates)
        count = sum([
            len(self.remaining_tasks[agent][task]) * self.num_replicates
            for agent in self.remaining_tasks
            for task in self.remaining_tasks[agent]
        ])
        print(
            ColorMessage.cyan(f"Message: {count} samples remaining ({self.num_replicates} replicates per model).")
        )

        for agent in self.remaining_tasks:
            agent_ = json.dumps(agent)
            tasks_ = len(self.remaining_tasks[agent])
            samples_ = sum([
                len(self.remaining_tasks[agent][task]) * self.num_replicates
                for task in self.remaining_tasks[agent]
            ])
            if samples_ == 0:
                continue
            print(
                ColorMessage.cyan(
                    f"Agent {agent_} needs to run {tasks_} tasks with total {samples_} samples ({self.num_replicates} replicates):"
                )
            )
            for task in self.remaining_tasks[agent]:
                print(
                    ColorMessage.cyan(
                        f"    Task {json.dumps(task)}: {len(self.remaining_tasks[agent][task]) * self.num_replicates} samples"
                    )
                )

        # Create agents

        for agent in self.remaining_tasks:
            self.agents[agent] = self.config.definition.agent[agent].create()

    def get_output_dir(self, agent: str, task: str, replicate: int = 1) -> str:
        return os.path.join(self.config.output, agent, f"replicate_{replicate}", task)

    def model_sequential_iterator(self, check_interval: float = 0.5) -> Iterator[Tuple[str, str, int, SampleIndex]]:
        """
        Sequential model iterator - processes one model completely before moving to next.
        Yields (agent, task, replicate, index) tuples.
        
        Model isolation: Each model runs all its samples (all replicates) before next model starts.
        Sample failures stay local to the model - no cross-model fallback.
        
        IMPORTANT: Controls concurrency to avoid overwhelming the task server.
        Only yields when there's available worker capacity.
        
        CRITICAL: Each replicate gets its own fresh copy of samples from task_indices.
        Retries from NOT_AVAILABLE are handled by checking remaining_tasks for samples
        that need to be retried within the same replicate.
        """
        # Get unique agents in order
        agents = list(self.remaining_tasks.keys())
        
        for agent in agents:
            # Model-isolated: process this model completely before moving to next
            for replicate in range(1, self.num_replicates + 1):
                print(ColorMessage.cyan(f"\n>>> Starting {agent} - Replicate {replicate}/{self.num_replicates}"))
                
                # Get all tasks for this agent from the ORIGINAL assignments, not remaining_tasks
                # remaining_tasks gets modified during execution (retries), so it's not reliable
                tasks = [a.task for a in self.config.assignments if a.agent == agent]
                
                if not tasks:
                    continue
                
                # Create a fresh queue for this replicate from task_indices
                replicate_queue: Dict[str, List[SampleIndex]] = {}
                for task in tasks:
                    if task in self.task_indices:
                        replicate_queue[task] = self.task_indices[task].copy()
                
                # Process all tasks for this replicate
                while True:
                    # Check if all tasks are done for this replicate
                    # Must check BOTH the local queue AND remaining_tasks (for retries)
                    has_samples = False
                    for task in tasks:
                        # Check local queue
                        if task in replicate_queue and replicate_queue[task]:
                            has_samples = True
                            break
                        # Check remaining_tasks for retries (samples that got NOT_AVAILABLE)
                        if agent in self.remaining_tasks and task in self.remaining_tasks[agent]:
                            if self.remaining_tasks[agent][task]:
                                has_samples = True
                                break
                    
                    if not has_samples:
                        break
                    
                    # Find next available task with samples in queue
                    found_task = None
                    found_index = None
                    
                    for task in tasks:
                        # First check the local queue
                        if task in replicate_queue and replicate_queue[task]:
                            # Check worker capacity
                            with self.assignment_lock:
                                if self.free_worker.agent.get(agent, 0) > 0 and self.free_worker.task.get(task, 0) > 0:
                                    found_task = task
                                    found_index = replicate_queue[task].pop(0)
                                    self.free_worker.agent[agent] -= 1
                                    self.free_worker.task[task] -= 1
                                    break
                        
                        # If local queue is empty, check remaining_tasks for retries
                        if found_task is None:
                            with self.assignment_lock:
                                if (agent in self.remaining_tasks and 
                                    task in self.remaining_tasks[agent] and 
                                    self.remaining_tasks[agent][task] and
                                    self.free_worker.agent.get(agent, 0) > 0 and 
                                    self.free_worker.task.get(task, 0) > 0):
                                    found_task = task
                                    found_index = self.remaining_tasks[agent][task].pop(0)
                                    self.free_worker.agent[agent] -= 1
                                    self.free_worker.task[task] -= 1
                                    break
                    
                    if found_task is not None:
                        # Found task with capacity and samples
                        assert found_index is not None, "found_task is not None but found_index is None"
                        yield agent, found_task, replicate, found_index
                    else:
                        # No capacity, wait
                        time.sleep(check_interval)

    def worker_generator(
        self, interval=10
    ) -> Iterator[Tuple[str, str, SampleIndex]]:

        node_list = ["SRC", "DST"]
        agent_node_index = {}
        task_node_index = {}
        for agent in self.agents:
            node_list.append(agent)
            agent_node_index[agent] = len(node_list) - 1
        for task in self.tasks:
            node_list.append(task)
            task_node_index[task] = len(node_list) - 1

        while True:

            # Step 0. Get real time task free worker

            with self.assignment_lock:
                for task in self.tasks:
                    self.free_worker.task[task] = self.tasks[task].get_concurrency()
                print("Running Count: {}".format(self.running_count))

            # Step 1. init edges: SRC -> agent -> task -> DST

            with self.assignment_lock:
                edges = {}
                for agent in self.agents:
                    edges[(0, agent_node_index[agent])] = self.free_worker.agent[agent]
                for task in self.tasks:
                    edges[(task_node_index[task], 1)] = self.free_worker.task[task]
                tot_remaining_samples = 0
                for agent in self.remaining_tasks:
                    for task in self.remaining_tasks[agent]:
                        tot_remaining_samples += len(self.remaining_tasks[agent][task])
                        edges[(agent_node_index[agent], task_node_index[task])] = len(
                            self.remaining_tasks[agent][task]
                        )
            if tot_remaining_samples == 0:
                if self.running_count == 0:
                    break
                else:
                    time.sleep(interval / 2 + random.random() * interval)
                    continue

            # Step 2. Create graph and calculate max flow

            graph = Graph(node_count=len(node_list), edges=edges)
            max_flow = MaxFlow(graph, src=0, dst=1)

            if max_flow.max_flow == 0:
                time.sleep(interval / 2 + random.random() * interval)
                continue

            # Step 3. yield all (agent, task, index) tuples

            for (src, dst), e in max_flow.edges_dict.items():
                if (
                    src not in agent_node_index.values()
                    or dst not in task_node_index.values()
                ):
                    continue
                if e.flow == 0:
                    continue
                agent = node_list[src]
                task = node_list[dst]
                for _ in range(e.flow):
                    with self.assignment_lock:
                        index = self.remaining_tasks[agent][task].pop()
                        self.free_worker.agent[agent] -= 1
                        self.free_worker.task[task] -= 1
                    print(ColorMessage.green(f"Assigned {agent}/{task}#{index}"))
                    yield agent, task, index

            # Step 4. sleep for a while
            time.sleep(interval / 2 + random.random() * interval)

    def start(self, tqdm_out=None):
        # Calculate total samples across all replicates
        self.started_count = sum([
            len(self.remaining_tasks[agent][task]) * self.num_replicates
            for agent in self.remaining_tasks
            for task in self.remaining_tasks[agent]
        ])
        
        # Use sequential model iterator (model-isolated execution)
        generator = self.model_sequential_iterator()
        
        self.overall_tqdm = tqdm(
            total=self.started_count,
            desc="Total",
            position=0,
            file=tqdm_out,
        )
        
        # Create progress bars for each (agent, replicate) combination
        for idx, agent in enumerate(self.remaining_tasks.keys()):
            for replicate in range(1, self.num_replicates + 1):
                key = f"{agent}_r{replicate}"
                total = sum([
                    len(self.remaining_tasks[agent][task])
                    for task in self.remaining_tasks[agent]
                ])
                self.tqdm_ordered_by_agent[key] = tqdm(
                    total=total,
                    desc=key,
                    position=len(self.tqdm_ordered_by_agent) + 1,
                    file=tqdm_out,
                )
        
        # Process samples using sequential iterator
        while True:
            try:
                agent, task, replicate, index = next(generator)
            except StopIteration:
                break
            self.start_worker(agent, task, replicate, index, self.finish_callback)

        self.overall_tqdm.close()
        for key in self.tqdm_ordered_by_agent:
            self.tqdm_ordered_by_agent[key].close()

        final_message = (
            f"\n\n============================================\n"
            + ColorMessage.cyan(f"Message: {self.started_count} sample(s) started. ")
            + f"\nReplicates per model: {self.num_replicates}\n"
            + ColorMessage.green(f"   >> {self.finished_count} sample(s) finished successfully.")
            + f"\n"
        )
        if self.started_count != self.finished_count:
            final_message += (
                ColorMessage.red(
                    f"   >> {self.started_count - self.finished_count} sample(s) failed."
                )
                + "\n"
            )
        final_message += (
            ColorMessage.cyan(
                f"   >> results are saved to {self.config.output}"
            )
            + "\n"
        )
        final_message += "============================================\n\n"
        print(final_message)

    def record_completion(
        self, agent: str, task: str, replicate: int, index: SampleIndex, result: TaskOutput
    ):
        # NEW: Per-replicate isolated completion buckets with idempotency
        # Structure: {agent: {task: {replicate: [completion_data]}}}
        # Each replicate has its own dedicated bucket - no cumulative mixing
        
        total_for_task = len(self.task_indices[task])
        
        with self.assignment_lock:
            # Initialize nested structures for this replicate
            if agent not in self.completions:
                self.completions[agent] = {}
            if task not in self.completions[agent]:
                self.completions[agent][task] = {}
            if replicate not in self.completions[agent][task]:
                self.completions[agent][task][replicate] = []
            
            # Initialize completed_indices for idempotency check
            if agent not in self.completed_indices:
                self.completed_indices[agent] = {}
            if task not in self.completed_indices[agent]:
                self.completed_indices[agent][task] = {}
            if replicate not in self.completed_indices[agent][task]:
                self.completed_indices[agent][task][replicate] = set()
            
            # IDEMPOTENCY CHECK: Skip if this sample already completed
            if index in self.completed_indices[agent][task][replicate]:
                print(ColorMessage.yellow(
                    f"[DUPLICATE IGNORED] agent={agent}, task={task}, replicate={replicate}, index={index}\n"
                    f"  Sample already completed, skipping duplicate callback"
                ))
                return
            
            # Mark this index as completed
            self.completed_indices[agent][task][replicate].add(index)
            
            # Store completion in the dedicated replicate bucket
            completion_data = {"index": index, "result": result}
            self.completions[agent][task][replicate].append(completion_data)
            
            # Count completions for this replicate (from dedicated bucket)
            replicate_count = len(self.completions[agent][task][replicate])
            
            # DEBUG: Log every completion
            print(ColorMessage.cyan(
                f"[COMPLETION] agent={agent}, task={task}, replicate={replicate}, index={index}\n"
                f"  Replicate {replicate} completions: {replicate_count}/{total_for_task}"
            ))
            
            # ONE-SHOT: Check if overall already triggered for this replicate
            if agent not in self.overall_triggered:
                self.overall_triggered[agent] = {}
            if task not in self.overall_triggered[agent]:
                self.overall_triggered[agent][task] = {}
            if replicate not in self.overall_triggered[agent][task]:
                self.overall_triggered[agent][task][replicate] = False
            
            if self.overall_triggered[agent][task][replicate]:
                print(ColorMessage.yellow(
                    f"[SKIP OVERALL] agent={agent}, task={task}, replicate={replicate}\n"
                    f"  Overall already triggered, completion count is {replicate_count}"
                ))
                return
            
            # Trigger calculate_overall ONLY when this replicate is complete AND first time
            if replicate_count >= total_for_task:
                # Mark as triggered BEFORE reading (one-shot guarantee)
                self.overall_triggered[agent][task][replicate] = True
                
                # Read directly from dedicated bucket
                replicate_completions = list(self.completions[agent][task][replicate])
                
                print(ColorMessage.yellow(
                    f"[TRIGGER calculate_overall] Replicate {replicate} complete with {replicate_count} samples"
                ))
                
                def calculate_overall_worker():
                    nonlocal agent, task, replicate
                    task_client = self.tasks[task]
                    
                    # Extract TaskOutput results from dedicated bucket
                    results = [c["result"] for c in replicate_completions if "result" in c]
                    
                    expected_count = len(self.task_indices.get(task, []))
                    actual_count = len(results)
                    
                    print(ColorMessage.yellow(
                        f"[DEBUG calculate_overall] agent={agent}, task={task}, replicate={replicate}\n"
                        f"  Completions in bucket: {len(replicate_completions)}\n"
                        f"  Results extracted: {actual_count}\n"
                        f"  Expected indices: {expected_count}"
                    ))
                    
                    if actual_count != expected_count:
                        print(ColorMessage.red(
                            f"[ERROR] calculate_overall called with {actual_count} results but expected {expected_count}!"
                        ))
                        return
                    
                    # STRONG SAFEGUARD: Validate consistency BEFORE writing overall.json
                    # Read indexes from runs.jsonl to ensure consistency
                    output_dir = self.get_output_dir(agent, task, replicate)
                    runs_jsonl_path = os.path.join(output_dir, "runs.jsonl")
                    runs_indexes = set()
                    if os.path.exists(runs_jsonl_path):
                        with open(runs_jsonl_path, "r", encoding="utf-8", errors="replace") as rf:
                            for rline in rf:
                                if rline.strip():
                                    try:
                                        rdata = json.loads(rline)
                                        runs_indexes.add(rdata.get("index"))
                                    except:
                                        pass
                    
                    expected_indexes = set(self.task_indices.get(task, []))
                    missing_in_runs = expected_indexes - runs_indexes
                    extra_in_runs = runs_indexes - expected_indexes
                    
                    if missing_in_runs or extra_in_runs:
                        print(ColorMessage.red(
                            f"[CRITICAL CONSISTENCY ERROR] {agent}/replicate_{replicate}/{task}:\n"
                            f"  Expected indexes: {sorted(expected_indexes)}\n"
                            f"  Found in runs.jsonl: {sorted(runs_indexes)}\n"
                            f"  MISSING from runs.jsonl: {sorted(missing_in_runs)}\n"
                            f"  EXTRA in runs.jsonl: {sorted(extra_in_runs)}\n"
                            f"  ABORTING overall.json write to prevent inconsistency!"
                        ))
                        # Don't write overall.json if there's a consistency issue
                        # Instead, write an error marker file
                        error_marker = {
                            "error": "consistency_check_failed",
                            "expected_indexes": sorted(expected_indexes),
                            "runs_indexes": sorted(runs_indexes),
                            "missing_in_runs": sorted(missing_in_runs),
                            "extra_in_runs": sorted(extra_in_runs),
                            "results_count": actual_count
                        }
                        with open(os.path.join(output_dir, "overall_INCONSISTENT.json"), "w", encoding="utf-8") as ef:
                            ef.write(json.dumps(error_marker, indent=4, ensure_ascii=False))
                        return
                    
                    # Consistency check passed - proceed with aggregation
                    overall = task_client.calculate_overall(results)
                    if isinstance(overall, dict):
                        overall["replicate"] = replicate
                    with open(
                        os.path.join(output_dir, "overall.json"), "w",
                        encoding="utf-8"
                    ) as f:
                        f.write(json.dumps(overall, indent=4, ensure_ascii=False))
                
                threading.Thread(target=calculate_overall_worker).start()

    def finish_callback(
        self, agent: str, task: str, replicate: int, index: SampleIndex, result: TaskClientOutput
    ):
        # EARLY IDEMPOTENCY CHECK: If this sample wasn't started by us, skip it
        # This prevents duplicate callbacks from triggering any work
        key = (agent, task, replicate)
        with self.assignment_lock:
            if key not in self.started_samples or index not in self.started_samples[key]:
                # Sample wasn't started by this assigner - ignore it
                print(ColorMessage.yellow(
                    f"[DUPLICATE IGNORED] {agent}/replicate_{replicate}/{task}#{index} - not started by this session"
                ))
                return
            # Remove from started_samples to prevent future duplicates
            self.started_samples[key].discard(index)
        
        # Handle NOT_AVAILABLE - this is a REAL task issue, not "no workers"
        # The controller returns 406 for both "task not found" AND "no workers available"
        # We need to distinguish between them
        if result.error == TaskError.NOT_AVAILABLE.value:
            info = result.info or ""
            if "No workers available" in info or "no workers" in info.lower():
                print(
                    ColorMessage.yellow(
                        f"Warning: {task} has no available workers, not retrying (would cause infinite loop)."
                    )
                )
            else:
                print(
                    ColorMessage.yellow(
                        f"Warning: {task} is not available for {agent}, retrying within model."
                    )
                )
                with self.assignment_lock:
                    self.remaining_tasks[agent][task].insert(0, index)
                    self.free_worker.agent[agent] += 1
                    self.free_worker.task[task] += 1
                    self.running_count -= 1
            return

        # Handle sample failure - record but NO cross-model fallback
        # Failures stay local to the current model
        if result.error is not None:
            print(ColorMessage.red(
                f"FAILURE: {agent}/replicate_{replicate}/{task}#{index} "
                f"error: {result.error} - {result.info}"
            ))

        # Write output with replicate info
        output_folder = self.get_output_dir(agent, task, replicate)
        os.makedirs(output_folder, exist_ok=True)
        timestamp: int = int(time.time() * 1000)
        time_str = datetime.datetime.fromtimestamp(timestamp / 1000).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        
        output_data = {
            "index": index,
            "replicate": replicate,
            "agent": agent,
            "task": task,
            **result.dict(),
            "time": {"timestamp": timestamp, "str": time_str},
        }
        
        write_to_file = json.dumps(output_data, ensure_ascii=False) + "\n"
        
        # FIX: Ensure runs.jsonl write is atomic with completion tracking
        # This prevents the race condition where completion is recorded but runs.jsonl write fails
        if not result.error:
            target_file = os.path.join(output_folder, "runs.jsonl")
            # Check if we actually have a valid output
            if result.output is not None:
                # CRITICAL: Write to runs.jsonl FIRST, inside the lock, to ensure consistency
                with self.assignment_lock:
                    try:
                        with open(target_file, "a+", encoding="utf-8") as f:
                            f.write(write_to_file)
                    except Exception as e:
                        print(ColorMessage.red(
                            f"ERROR writing runs.jsonl: {agent}/replicate_{replicate}/{task}#{index}: {e}"
                        ))
                    # Then update counters
                    self.finished_count += 1
                # Record completion outside the lock (safe - uses its own lock)
                self.record_completion(agent, task, replicate, index, result.output)
                # Safe update with None check
                if self.overall_tqdm is not None:
                    self.overall_tqdm.update(1)
                key = f"{agent}_r{replicate}"
                if key in self.tqdm_ordered_by_agent and self.tqdm_ordered_by_agent[key] is not None:
                    self.tqdm_ordered_by_agent[key].update(1)
                print(ColorMessage.green(f"SUCCESS: {agent}/replicate_{replicate}/{task}#{index}"))
            else:
                # No error but also no output - this is suspicious
                # Don't count as finished, don't update progress
                print(ColorMessage.red(
                    f"WARNING: {agent}/replicate_{replicate}/{task}#{index} completed but output is NULL"
                ))
                # Still record this as a completion attempt with null output
                with self.assignment_lock:
                    self.finished_count += 1  # Count as attempted
                    # Still write to runs.jsonl for traceability
                    try:
                        with open(target_file, "a+", encoding="utf-8") as f:
                            f.write(write_to_file)
                    except Exception as e:
                        print(ColorMessage.red(
                            f"ERROR writing runs.jsonl (null output): {e}"
                        ))
                if self.overall_tqdm is not None:
                    self.overall_tqdm.update(1)
                key = f"{agent}_r{replicate}"
                if key in self.tqdm_ordered_by_agent and self.tqdm_ordered_by_agent[key] is not None:
                    self.tqdm_ordered_by_agent[key].update(1)
        else:
            target_file = os.path.join(output_folder, "error.jsonl")
            # Count failed samples - write to error.jsonl inside lock
            with self.assignment_lock:
                self.finished_count += 1
                try:
                    with open(target_file, "a+", encoding="utf-8") as f:
                        f.write(write_to_file)
                except Exception as e:
                    print(ColorMessage.red(
                        f"ERROR writing error.jsonl: {e}"
                    ))
            if self.overall_tqdm is not None:
                self.overall_tqdm.update(1)
            key = f"{agent}_r{replicate}"
            if key in self.tqdm_ordered_by_agent and self.tqdm_ordered_by_agent[key] is not None:
                self.tqdm_ordered_by_agent[key].update(1)

        with self.assignment_lock:
            self.free_worker.agent[agent] += 1
            self.free_worker.task[task] += 1
            self.running_count -= 1

    def start_worker(
        self,
        agent: str,
        task: str,
        replicate: int,
        index: SampleIndex,
        finish_callback: Union[
            Callable[[str, str, int, SampleIndex, TaskClientOutput], None], None
        ] = None,
    ):
        # Track that this sample was started - used to prevent duplicate progress updates
        with self.assignment_lock:
            key = (agent, task, replicate)
            if key not in self.started_samples:
                self.started_samples[key] = set()
            self.started_samples[key].add(index)
        
        def worker_thread():
            nonlocal agent, task, replicate, index, finish_callback

            result = self.tasks[task].run_sample(index, self.agents[agent])

            if finish_callback:
                finish_callback(agent, task, replicate, index, result)

        with self.assignment_lock:
            self.running_count += 1
        threading.Thread(target=worker_thread).start()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config", "-c", type=str, default="configs/assignments/default.yaml"
    )
    parser.add_argument(
        "--auto-retry", "-r", action="store_true", dest="retry"
    )
    parser.add_argument(
        "--num-replicates", "-n", type=int, default=3,
        help="Number of replicates to run (default: 3)"
    )
    parser.add_argument(
        "--model-isolated", "-m", action="store_true", default=True,
        help="Run each model completely before moving to next (default: True)"
    )
    parser.add_argument(
        "--cross-model-fallback", action="store_true", default=False,
        help="Allow fallback to other models on sample failure (default: False)"
    )
    parser.add_argument(
        "--agent", "-a", type=str, default=None,
        help="Run specific agent only (non-interactive mode)"
    )
    args = parser.parse_args()

    print(f"\nConfiguration:")
    print(f"  Model Isolation: {args.model_isolated}")
    print(f"  Cross-Model Fallback: {args.cross_model_fallback}")
    print(f"  Number of Replicates: {args.num_replicates}")

    loader = ConfigLoader()
    config_ = loader.load_from(args.config)
    value = AssignmentConfig.parse_obj(config_)
    value = AssignmentConfig.post_validate(value)
    
    # Dynamic model loading from config - no hardcoded limits
    available_agents = list(value.definition.agent.keys())
    
    # Filter to exactly 8 target OpenRouter models
    target_models = [
        "gpt-5-mini",
        "gemini-3.1-flash-lite", "claude-haiku-4.5", "xiaomi-mimo-v2-pro",
        "z-ai-glm-5", "gemma-3-27b-it", "nemotron-3-nano-30b", "gpt-oss-20b"
    ]
    openrouter_agents = [a for a in available_agents if a in target_models]
    
    # Non-interactive mode: run specific agent
    if args.agent:
        if args.agent in openrouter_agents:
            for assignment in value.assignments:
                assignment.agent = args.agent
            print(f"\nRunning single model: {args.agent} x {args.num_replicates} replicates")
        else:
            print(f"\nError: Agent '{args.agent}' not found in available models")
            print(f"Available: {openrouter_agents}")
            sys.exit(1)
    elif openrouter_agents:
        # Interactive mode - only show menu if no specific agent
        print("\nAvailable OpenRouter models:")
        for idx, agent in enumerate(openrouter_agents, 1):
            print(f"  {idx}. {agent}")
        print("  (Press Enter to run all 8 target models)")
        
        choice = input("\nEnter choice (or press Enter for all 8): ").strip()
        if choice:
            try:
                selected_model = openrouter_agents[int(choice) - 1]
                # Override agent in assignments to run single model
                for assignment in value.assignments:
                    assignment.agent = selected_model
                print(f"\nSelected model: {selected_model}")
            except (IndexError, ValueError):
                print("\nInvalid selection, running all 8 target models")
        else:
            # Filter assignments to only include the 8 target models
            filtered_assignments = [a for a in value.assignments if a.agent in target_models]
            value.assignments = filtered_assignments
            print(f"\nRunning {len(filtered_assignments)} target models x {args.num_replicates} replicates")
    else:
        print("\nNo OpenRouter models found in config")
    
    v = value.dict()
    with std_out_err_redirect_tqdm() as orig_stdout:
        Assigner(
            value,
            auto_retry=args.retry,
            num_replicates=args.num_replicates,
            model_isolated=args.model_isolated,
            cross_model_fallback=args.cross_model_fallback
        ).start(tqdm_out=orig_stdout)
