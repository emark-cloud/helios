import { Bytes } from "@graphprotocol/graph-ts";
import { Committed } from "../generated/OraclePriceAnchor/OraclePriceAnchor";
import { OraclePriceCommit } from "../generated/schema";
import { logEventId } from "./helpers";

// `OraclePriceAnchor.Committed(index, root, windowStart, windowEnd, signer)`
// — EIP-712-signed Poseidon root chain consumed by momentum / mean-reversion
// circuits via `priceAnchor.isKnownRoot(root)`.
export function handlePriceCommitted(event: Committed): void {
  const row = new OraclePriceCommit(logEventId(event));
  row.index = event.params.index;
  row.root = event.params.root;
  row.windowStart = event.params.windowStart;
  row.windowEnd = event.params.windowEnd;
  row.signer = event.params.signer as Bytes;
  row.committedAt = event.block.timestamp;
  row.txHash = event.transaction.hash;
  row.save();
}
