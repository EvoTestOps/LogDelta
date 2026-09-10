### Label analysis revisited
What follows is a analysis done, way after the video, on 10 Sep 2026 on the label correctness of  
PageRank_MachineDown_application_1445062781478_0015 folder. 

Turns out that label was indeed correct although [video script](video_script.md) claimed it was disk full anomaly. 

The analysis was done with [LogLead MCP server](https://github.com/EvoTestOps/LogLead) using [Goose](https://github.com/aaif-goose/goose) 
as MCP-client with google/gemini-3.7-flash via OpenRouter as LLM backend. 
### Analysis chat
> what about MachineDown_...*0015 is it really machinedown


· Exceeded auto-compact threshold of 80%. Performing auto-compaction...

· Compaction complete

  ────────────────────────────────────────
  ▸ list_log_roots loglead


  ────────────────────────────────────────
  ▸ search_log_lines loglead
    folders: PageRank_MachineDown_application_1445062781478_0015
    pattern: .*
    regex: true
    session_id: hadoop_renamed-a8b176aa


  ────────────────────────────────────────
  ▸ search_log_lines loglead
    regex: true
    pattern: WARN|FATAL|ERROR|Exception|failed|lost|killed|disconnection|shutting|exit
    ignore_case: true
    session_id: hadoop_renamed-a8b176aa
    folders: PageRank_MachineDown_application_1445062781478_0015


  ────────────────────────────────────────
  ▸ search_log_lines loglead
    regex: true
    pattern: lost|dead|unhealthy|heartbeat|node
    folders: PageRank_MachineDown_application_1445062781478_0015
    session_id: hadoop_renamed-a8b176aa

**Yes, `PageRank_MachineDown_application_1445062781478_0015` is genuinely a `MachineDown` run.**

The explicit evidence in the logs confirms that a target node (`10.86.164.9`) went down during execution, causing cascading communication failures and exclusions:

---

### Key Evidence in `application_1445062781478_0015`:

1. **Dead DataNode Exclusions:**
   - The HDFS DFSClient failed to communicate with the downed node and repeatedly excluded it:
     ```text
     INFO [Thread-56] org.apache.hadoop.hdfs.DFSClient: Exception in createBlockOutputStream
     java.io.IOException: Bad connect ack with firstBadLink as 10.86.164.9:50010
     INFO [Thread-56] org.apache.hadoop.hdfs.DFSClient: Excluding datanode 10.86.164.9:50010
     ```

2. **Forcibly Closed Sockets / Network Disconnections:**
   - Active connections to/from client nodes were abruptly broken when the machine stopped responding:
     ```text
     INFO [Socket Reader #1 for port 40658] org.apache.hadoop.ipc.Server:
     readAndProcess from client 172.22.149.145 threw exception [java.io.IOException: An existing connection was forcibly closed by the remote host]
     ```

3. **Orphaned Containers & Retried Attempts:**
   - The Resource Manager reported container loss:
     ```text
     ERROR [RMCommunicator Allocator] RMContainerAllocator: Container complete event for unknown container id container_1445062781478_0015_01_00012
     ```
   - Multiple container attempts (`attempt_..._m_000001_0`, `attempt_..._m_000002_0`, `attempt_..._m_000005_0`) had to be killed and retried (`_1`) due to lost node communication.

### Summary
Unlike runs where fault injection failed or produced no errors, **`..._0015` contains full, verifiable symptoms of a node going down** (HDFS DataNode failure/exclusion, socket termination, and lost container states). Its label **`MachineDown` is correct**.
  ⏱ 35.33s
  ━━━━╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌ 21% 27k/128k
> is there any indication that there is lack of space in that run


  ────────────────────────────────────────
  ▸ search_log_lines loglead
    folders: PageRank_MachineDown_application_1445062781478_0015
    session_id: hadoop_renamed-a8b176aa
    regex: true
    ignore_case: true
    pattern: space|full|quota|DiskOutOfSpaceException|No space left on device|There is not enough space


  ────────────────────────────────────────
  ▸ search_log_lines loglead
    pattern: disk
    ignore_case: true
    session_id: hadoop_renamed-a8b176aa
    folders: PageRank_MachineDown_application_1445062781478_0015
    regex: true

**No, there is no disk space exhaustion (DiskFull) in this run.**

Here is the distinction in the log messages:

1. **YARN Scheduling Slot "Space" (Resource Allocation, not Disk Space):**
   There are messages from `RMContainerAllocator` stating:
   ```text
   INFO [RMCommunicator Allocator] RMContainerAllocator: Going to preempt 1 due to lack of space for maps
   ```
   In YARN/MapReduce terminology, *"lack of space for maps"* refers to **cluster execution slots / memory capacity** (the Resource Manager preempting reduce containers to free up container slots for pending map tasks), not physical hard drive storage.

2. **Standard MapReduce On-Disk Spilling:**
   Lines mentioning disk (e.g., `Shuffling to disk since ... is greater than maxSingleShuffleLimit` and `Merging 10 files ... from disk`) represent routine MapReduce in-memory vs. on-disk buffer behavior during shuffle/sort phases.

3. **Absence of Disk-Full Fault Symptoms:**
   None of the actual disk exhaustion errors (such as `FATAL: There is not enough space on the disk`, `DiskOutOfSpaceException`, or `No space left on device`) occur anywhere in this log run.
  ⏱ 11.98s
  ━━━━━╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌ 27% 34k/128k
