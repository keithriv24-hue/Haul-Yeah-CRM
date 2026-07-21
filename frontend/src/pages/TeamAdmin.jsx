import React from "react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { InstructionBanner } from "@/components/Bits";
import { AdminCreditsTab } from "@/components/team/AdminCreditsTab";
import { AdminBadgesTab } from "@/components/team/AdminBadgesTab";
import { AdminChallengesTab } from "@/components/team/AdminChallengesTab";
import { AdminInsightsTab, AdminLogTab } from "@/components/team/AdminInsightsTabs";

export default function TeamAdmin() {
  return (
    <div data-testid="team-admin-page" className="space-y-4">
      <div>
        <h1 className="font-display text-3xl sm:text-4xl font-extrabold tracking-tight text-[#1B2A4A]">Team HQ</h1>
        <p className="text-sm text-slate-500 mt-1">Job credits, badges, challenges, and who's earning what. Only you can see this.</p>
      </div>
      <InstructionBanner testId="team-admin-banner">
        Everything starts at zero from launch day — approve tallies as jobs finish and badges unlock on their own. Every action here is logged.
      </InstructionBanner>
      <Tabs defaultValue="credits">
        <TabsList className="flex-wrap h-auto">
          <TabsTrigger data-testid="admin-tab-credits" value="credits">Credits</TabsTrigger>
          <TabsTrigger data-testid="admin-tab-badges" value="badges">Badges</TabsTrigger>
          <TabsTrigger data-testid="admin-tab-challenges" value="challenges">Challenges</TabsTrigger>
          <TabsTrigger data-testid="admin-tab-insights" value="insights">Crew insight</TabsTrigger>
          <TabsTrigger data-testid="admin-tab-log" value="log">Log</TabsTrigger>
        </TabsList>
        <TabsContent value="credits"><AdminCreditsTab /></TabsContent>
        <TabsContent value="badges"><AdminBadgesTab /></TabsContent>
        <TabsContent value="challenges"><AdminChallengesTab /></TabsContent>
        <TabsContent value="insights"><AdminInsightsTab /></TabsContent>
        <TabsContent value="log"><AdminLogTab /></TabsContent>
      </Tabs>
    </div>
  );
}
