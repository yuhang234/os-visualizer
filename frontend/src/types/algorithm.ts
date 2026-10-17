/**
 * 算法轨迹与步骤快照类型（设计文档 §4.1 步骤数据结构 + §13.3 契约）。
 * 字段名与后端 `backend/app/engine/*.py` 产出的 JSON 严格一一对应。
 */

export type PageAlgorithm = 'FIFO' | 'LRU' | 'OPT' | 'CLOCK';

export type AlgorithmId =
  | 'fifo'
  | 'lru'
  | 'opt'
  | 'clock'
  | 'banker-safety'
  | 'banker-request'
  | 'threads-pc';

export type EventTone = 'NONE' | 'STEP' | 'HIT' | 'MISS' | 'SUCCESS' | 'DANGER' | 'BLOCK' | 'WAKEUP';

export type LogLevel = 'INFO' | 'SUCCESS' | 'WARN' | 'DANGER';

export interface StepLog {
  timestamp: string;
  level: LogLevel;
  message: string;
}

export interface TraceStep<S = unknown> {
  stepIndex: number;
  title: string;
  description: string;
  snapshot: S;
  highlights: string[];
  logs: StepLog[];
  eventTone: EventTone;
}

export interface ExecutionTrace<S = unknown, M = unknown> {
  algorithmId: AlgorithmId;
  algorithmName: string;
  createdAt: string;
  totalSteps: number;
  initialState: unknown;
  steps: TraceStep<S>[];
  metrics?: M;
}

export interface TraceMetrics {
  totalAccess?: number;
  hits?: number;
  misses?: number;
  hitRate?: number;
  missRate?: number;
  [key: string]: number | undefined;
}

/* ------------------------------ 页面置换 ------------------------------ */

export type FrameStatus = 'EMPTY' | 'IDLE' | 'HIT' | 'MISS';
export type PageStatus = 'HIT' | 'MISS' | 'NONE';

export interface PageRepSnapshot {
  algorithm: PageAlgorithm;
  frameCount: number;
  frames: (number | null)[];
  frameStatus: FrameStatus[];
  residentTime: number[];
  page: number | null;
  status: PageStatus;
  evictedPage: number | null;
  evictedFrameIndex: number | null;
  hits: number;
  misses: number;
  accessedCount: number;
  totalAccess: number;
  hitRate: number;
  missRate: number;
  stepIndex: number;
  fifoQueue: number[];
  lruOrder: number[];
  clockPointer: number | null;
  clockRefBits: number[] | null;
  clockSweep?: number[];
}

export interface PageRepInitialState {
  algorithm: PageAlgorithm;
  frameCount: number;
  referenceString: number[];
  description: string;
}

export type PageRepTrace = ExecutionTrace<PageRepSnapshot> & {
  finalFrames: (number | null)[];
  initialState: PageRepInitialState;
};

/* ------------------------------ 银行家 ------------------------------ */

export type SafetyPhase = 'INIT' | 'COMPLETE' | 'SKIP' | 'FINAL';

export interface SafetyRow {
  process: string;
  workBefore: number[];
  need: number[];
  allocation: number[];
  workAfter: number[];
  finish: boolean;
}

export interface BankerSafetySnapshot {
  phase: SafetyPhase;
  work: number[];
  workBefore: number[];
  workAfter: number[];
  finish: boolean[];
  safeSequence: string[];
  rows: SafetyRow[];
  processIndex: number | null;
  process: string | null;
  satisfied: boolean | null;
  need: number[] | null;
  allocation: number[] | null;
  remainingProcesses: string[];
  isSafe: boolean | null;
}

export type RequestPhase =
  | 'REQUEST'
  | 'CHECK_NEED'
  | 'CHECK_AVAILABLE'
  | 'REJECT'
  | 'WAIT'
  | 'TENTATIVE'
  | 'GRANT'
  | 'ROLLBACK';

export interface BankerRequestSnapshot {
  phase: RequestPhase;
  process: string;
  processIndex: number;
  request: number[];
  available: number[];
  need: number[];
  allocation: number[];
  checkNeed: boolean | null;
  checkAvailable: boolean | null;
  granted: boolean | null;
  rolledBack: boolean;
  isSafeAfterTentative?: boolean | null;
  safeSequence?: string[];
  reason?: string;
  availableBefore?: number[];
  availableAfter?: number[];
  needAfter?: number[];
  allocationAfter?: number[];
}

export interface BankerState {
  available: number[];
  maxMatrix: number[][];
  allocationMatrix: number[][];
  needMatrix?: number[][];
  processCount: number;
  resourceCount: number;
  processNames: string[];
  resourceNames: string[];
}

export type BankerSafetyTrace = ExecutionTrace<BankerSafetySnapshot> & { state: BankerState };
export type BankerRequestTrace = ExecutionTrace<BankerRequestSnapshot | BankerSafetySnapshot> & { state: BankerState };

export interface BankerSafetyResult {
  isSafe: boolean;
  safeSequence: string[];
  unfinishedProcesses: string[];
  steps: TraceStep<BankerSafetySnapshot>[];
  trace: BankerSafetyTrace;
  state: BankerState;
}

export interface BankerRequestResult {
  granted: boolean;
  reason: string;
  checkNeed: boolean | null;
  checkAvailable: boolean | null;
  isSafeAfterTentative: boolean | null;
  safeSequence: string[];
  resultingAvailable?: number[] | null;
  resultingAllocation?: number[] | null;
  resultingNeed?: number[][] | null;
  steps: TraceStep<BankerRequestSnapshot | BankerSafetySnapshot>[];
  trace: BankerRequestTrace;
}

/* ------------------------------ 多线程 ------------------------------ */

export type ThreadType = 'PRODUCER' | 'CONSUMER';
export type ThreadLifecycle = 'NEW' | 'RUNNING' | 'BLOCKED' | 'SLEEP' | 'DONE';

export type ThreadAction =
  | 'INIT'
  | 'PRODUCE'
  | 'P_EMPTY'
  | 'BLOCK_EMPTY'
  | 'P_MUTEX'
  | 'BLOCK_MUTEX'
  | 'INSERT'
  | 'V_MUTEX'
  | 'V_FULL'
  | 'P_FULL'
  | 'BLOCK_FULL'
  | 'REMOVE'
  | 'V_EMPTY'
  | 'CONSUME'
  | 'DONE'
  | 'FINISH';

export interface ThreadInfo {
  id: string;
  name: string;
  type: ThreadType;
  state: ThreadLifecycle;
  progress: number;
  opsDone: number;
  opsQuota: number;
  currentLine: number;
  blockedOn: string | null;
  lastAction: string;
  produced: number;
  consumed: number;
  waitEvents: number;
  wakeEvents: number;
  code: string[];
}

export interface ThreadsCounters {
  produced?: number;
  consumed?: number;
  blockEvents?: number;
  mutexBlockEvents?: number;
  wakeEvents?: number;
  contextSwitches?: number;
  [key: string]: number | undefined;
}

export interface ThreadsSnapshot {
  time: number;
  bufferState: (number | null)[];
  bufferCount: number;
  inPointer: number;
  outPointer: number;
  semaphores: { mutex: number; empty: number; full: number };
  mutexOwner: string | null;
  waitQueues: { mutex: string[]; empty: string[]; full: string[] };
  activeThreadId: string | null;
  activeThreadType: ThreadType | null;
  activeLine: number | null;
  action: ThreadAction;
  threads: ThreadInfo[];
  counters: ThreadsCounters;
}

export interface ThreadsMetrics {
  bufferCapacity: number;
  produced: number;
  consumed: number;
  bufferRemaining: number;
  blockEvents: number;
  mutexBlockEvents: number;
  wakeEvents: number;
  contextSwitches: number;
  virtualDuration: number;
  criticalTime: number;
  completedThreads: number;
  blockedThreads: number;
  truncated: boolean;
}

export type ThreadsInvariants = Record<string, boolean>;

export type ThreadsTrace = ExecutionTrace<ThreadsSnapshot, ThreadsMetrics> & {
  invariants: ThreadsInvariants;
};

/* ------------------------------ 请求体 ------------------------------ */

export interface PageReplacementRequest {
  algorithm: PageAlgorithm;
  referenceString: number[];
  frameCount: number;
}

export interface BankerRequestPayload {
  processIndex: number;
  requestVector: number[];
  currentState: {
    available: number[];
    maxMatrix: number[][];
    allocationMatrix: number[][];
  };
}

export interface ThreadsRequest {
  bufferCapacity: number;
  producerCount: number;
  consumerCount: number;
  totalOperations: number;
  productionTime: number;
  consumptionTime: number;
  criticalTime: number;
  seed: number;
}

/* ------------------------------ 前端辅助 ------------------------------ */

export type PlaybackStatus = 'IDLE' | 'LOADING' | 'READY' | 'PLAYING' | 'FINISHED';

export const PLAYBACK_SPEEDS = [0.5, 1, 2, 4, 8] as const;
export type PlaybackSpeed = (typeof PLAYBACK_SPEEDS)[number];

/** 速度档位 → 每步毫秒数（设计文档 §4.3） */
export const SPEED_INTERVAL_MS: Record<PlaybackSpeed, number> = {
  0.5: 2000,
  1: 1000,
  2: 500,
  4: 250,
  8: 125,
};
