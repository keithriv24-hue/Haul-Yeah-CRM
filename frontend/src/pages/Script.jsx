import React from "react";
import { Download } from "lucide-react";
import { InstructionBanner, PageTitle } from "@/components/Bits";
import { Button } from "@/components/ui/button";
import { ScriptPanel } from "@/components/ScriptPanel";

export default function Script() {
  return (
    <div data-testid="script-page" className="max-w-2xl">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <PageTitle title="Sales Script" subtitle="Weekend move phone script — matches the Scope Calculator exactly." />
        <Button asChild variant="outline" size="sm" className="gap-1.5 mb-4" data-testid="script-download-btn">
          <a href="/haul-yeah-phone-script.docx" download>
            <Download className="w-3.5 h-3.5" /> Word copy
          </a>
        </Button>
      </div>
      <InstructionBanner>
        The words in orange boxes are ready to say out loud. Run the Scope Calculator live while you follow this, top to bottom. Never mention costs, crew pay, or the cushion.
      </InstructionBanner>
      <ScriptPanel defaultOpen={["opening", "scope", "access", "special", "quote", "objections", "close", "notready"]} />
    </div>
  );
}
