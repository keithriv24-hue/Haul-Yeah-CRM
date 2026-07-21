import React from "react";
import { InstructionBanner, PageTitle } from "@/components/Bits";
import { ScriptPanel } from "@/components/ScriptPanel";

export default function Script() {
  return (
    <div data-testid="script-page" className="max-w-2xl">
      <PageTitle title="Sales Script" subtitle="What to say on every call, top to bottom." />
      <InstructionBanner>
        The words in orange boxes are ready to say out loud. This same script sits next to the Quote Calculator so you can read and price at the same time.
      </InstructionBanner>
      <ScriptPanel defaultOpen={["opening", "scope", "access", "special", "distance", "timing", "close"]} />
    </div>
  );
}
