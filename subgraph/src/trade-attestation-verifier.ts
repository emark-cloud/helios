import { Bytes } from "@graphprotocol/graph-ts";
import { VerifierRegistered } from "../generated/TradeAttestationVerifier/TradeAttestationVerifier";
import { VerifierRegistration } from "../generated/schema";
import { logEventId } from "./helpers";

export function handleVerifierRegistered(event: VerifierRegistered): void {
  const r = new VerifierRegistration(logEventId(event));
  r.declaredClass = event.params.declaredClass;
  r.verifier = event.params.verifier as Bytes;
  r.registeredAt = event.block.timestamp;
  r.txHash = event.transaction.hash;
  r.save();
}
