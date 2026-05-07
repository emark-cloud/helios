/**
 * Withdraw control. DESIGN.md §9.3 — "always visible, never hidden
 * behind menus."
 *
 * Phase 4 (WS-FE-1) wires the affordance to a single-passkey userOp
 * via `usePassport()`. When Passport is disabled (anvil/dev), the
 * button stays gated with the same explainer it carried in Phase 1 —
 * the e2e harness withdraws via deterministic anvil signers, not
 * through this surface.
 */

"use client";

import { useState } from "react";
import { encodeFunctionData, parseUnits, type Hex } from "viem";

import { Numeric } from "@/components/atoms/Numeric";
import { usePassport } from "@/components/passport/PassportProvider";
import { addressesForChainId } from "@/lib/addresses";
import { formatUsd } from "@/lib/format";
import { IUserVaultAbi } from "@helios/contracts-abi";

const KITE_CHAIN_ID = Number(process.env.NEXT_PUBLIC_KITE_CHAIN_ID ?? "2368");
const USDC_DECIMALS = 6;

export function WithdrawControl({ totalNavUsd }: { totalNavUsd: number }): JSX.Element {
  const passport = usePassport();
  const [state, setState] = useState<
    | { kind: "idle" }
    | { kind: "submitting" }
    | { kind: "ok"; txHash: string }
    | { kind: "error"; message: string }
  >({ kind: "idle" });

  const passportReady = passport.enabled && passport.session !== null && passport.bundle !== null;

  async function onWithdraw(): Promise<void> {
    if (!passportReady || passport.session === null || passport.bundle === null) return;
    const addrs = addressesForChainId(KITE_CHAIN_ID);
    if (!addrs.userVault || !addrs.usdc) {
      setState({
        kind: "error",
        message: "kite-testnet deployment is missing userVault / usdc.",
      });
      return;
    }
    setState({ kind: "submitting" });
    try {
      const amount = parseUnits(totalNavUsd.toString(), USDC_DECIMALS);
      const callData: Hex = encodeFunctionData({
        abi: IUserVaultAbi,
        functionName: "withdraw",
        args: [addrs.usdc, amount],
      });
      const result = await passport.bundle.aaSdk.sendUserOperationAndWait(
        passport.session.aaAddress,
        { targets: [addrs.userVault], callDatas: [callData] },
        passport.bundle.signFn,
      );
      if (result.status.status !== "success" && result.status.status !== "included") {
        throw new Error(result.status.reason ?? `withdraw failed: ${result.status.status}`);
      }
      setState({ kind: "ok", txHash: result.status.transactionHash ?? result.userOpHash });
    } catch (err) {
      const message = err instanceof Error ? err.message : "Withdraw failed.";
      setState({ kind: "error", message });
    }
  }

  return (
    <div className="flex items-center justify-between gap-4 rounded-md border border-surface-line bg-surface-panel px-4 py-3">
      <div>
        <div className="text-[12px] uppercase tracking-[0.16em] text-fg-muted">Withdrawable</div>
        <div className="mt-1 text-base">
          <Numeric>{formatUsd(totalNavUsd, { cents: false })}</Numeric>
        </div>
        {state.kind === "error" ? (
          <p className="mt-1 font-mono text-[12px] text-signal-negative">{state.message}</p>
        ) : null}
        {state.kind === "ok" ? (
          <p className="mt-1 font-mono text-[12px] text-signal-positive">
            Withdrawn — tx {shorten(state.txHash)}
          </p>
        ) : null}
      </div>
      <button
        type="button"
        onClick={() => void onWithdraw()}
        disabled={!passportReady || state.kind === "submitting"}
        className="rounded-sm border border-amber/60 px-3 py-2 font-mono text-xs uppercase tracking-[0.16em] text-amber-bright hover:bg-amber/10 disabled:cursor-not-allowed disabled:border-fg-muted/40 disabled:text-fg-muted disabled:hover:bg-transparent"
        title={
          passportReady
            ? "Withdraw the full NAV to your AA wallet via one passkey prompt"
            : "Sign in with Passport to enable withdraws"
        }
      >
        {state.kind === "submitting" ? "Withdrawing…" : "Withdraw"}
      </button>
    </div>
  );
}

function shorten(hash: string): string {
  if (hash.length < 12) return hash;
  return `${hash.slice(0, 6)}…${hash.slice(-4)}`;
}
