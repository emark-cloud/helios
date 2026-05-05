import { Bytes } from "@graphprotocol/graph-ts";
import { Committed } from "../generated/OracleYieldAnchor/OracleYieldAnchor";
import { OracleYieldCommit } from "../generated/schema";
import { logEventId } from "./helpers";

// `OracleYieldAnchor.Committed(index, root, windowStart, windowEnd, signer)`
// — same shape as price; consumed by yield_rotation_v1 via
// `yieldAnchor.isKnownRoot(root)`.
export function handleYieldCommitted(event: Committed): void {
  const row = new OracleYieldCommit(logEventId(event));
  row.index = event.params.index;
  row.root = event.params.root;
  row.windowStart = event.params.windowStart;
  row.windowEnd = event.params.windowEnd;
  row.signer = event.params.signer as Bytes;
  row.committedAt = event.block.timestamp;
  row.txHash = event.transaction.hash;
  row.save();
}
