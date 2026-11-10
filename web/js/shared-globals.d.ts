/* Type declarations for the globals the classic browser scripts share.
   The pages load these files as ordered <script> tags, so the names below are
   real globals on the page's window. Tickets 06 and 07 replace the shared
   clients with ES module imports, after which these declarations can shrink to
   the standard browser globals. */

interface JournalEntry {
  id?: string;
  name?: string;
  portion?: string;
  calories?: number;
  protein?: number;
  carbs?: number;
  fat?: number;
  meal?: string;
  date?: string;
}

interface JournalDocument {
  calorie_goal: number;
  entries: JournalEntry[];
}

interface TimeoutChannel {
  serverMs: number | null;
  waitMs: number;
}

interface ClientConfig {
  source: 'server' | 'fallback';
  error: string | null;
  provider: string;
  model: string;
  parse: TimeoutChannel;
  cook: TimeoutChannel;
  image: TimeoutChannel;
}

interface ConfigGlobal {
  FALLBACK_MS: number;
  load(fetchImpl?: typeof fetch): Promise<ClientConfig>;
  fromPayload(payload: unknown): ClientConfig;
  fallback(error: unknown): ClientConfig;
  channelFor(config: ClientConfig | null | undefined, kind: string): TimeoutChannel;
  describeFallback(config: ClientConfig): string;
}

interface JournalClaim {
  moved: number;
  skipped: number;
  document: JournalDocument | null;
}

interface JournalStoreGlobal {
  read(): Promise<JournalDocument>;
  addEntries(entries: JournalEntry[]): Promise<JournalDocument>;
  updateEntries(id: string, entries: JournalEntry[]): Promise<JournalDocument>;
  removeEntry(id: string): Promise<JournalDocument>;
  setGoal(goal: number): Promise<JournalDocument>;
  claimBrowserEntries(current: JournalDocument): Promise<JournalClaim>;
}

declare var Config: ConfigGlobal;
declare var JournalStore: JournalStoreGlobal;

interface Window {
  Config: ConfigGlobal;
  JournalStore: JournalStoreGlobal;
  __toastTid: ReturnType<typeof setTimeout> | undefined;
}
