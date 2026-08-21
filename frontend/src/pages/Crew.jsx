import React from "react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { TeamTab } from "@/components/crew/TeamTab";
import { ScheduleTab } from "@/components/crew/ScheduleTab";
import { AvailabilityTab } from "@/components/crew/AvailabilityTab";
import { TimeTab } from "@/components/crew/TimeTab";
import { MapTab } from "@/components/crew/MapTab";
import { ReportTab } from "@/components/crew/ReportTab";

export default function Crew() {
  return (
    <div data-testid="crew-page" className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold text-primary">Crew</h1>
        <p className="text-sm text-faint">Your team, their schedule, their hours, and payroll — all in one spot.</p>
      </div>
      <Tabs defaultValue="team">
        <TabsList>
          <TabsTrigger data-testid="crew-tab-team" value="team">Team</TabsTrigger>
          <TabsTrigger data-testid="crew-tab-schedule" value="schedule">Schedule</TabsTrigger>
          <TabsTrigger data-testid="crew-tab-availability" value="availability">Availability</TabsTrigger>
          <TabsTrigger data-testid="crew-tab-time" value="time">Time clock</TabsTrigger>
          <TabsTrigger data-testid="crew-tab-map" value="map">Live map</TabsTrigger>
          <TabsTrigger data-testid="crew-tab-report" value="report">Report</TabsTrigger>
        </TabsList>
        <TabsContent value="team"><TeamTab /></TabsContent>
        <TabsContent value="schedule"><ScheduleTab /></TabsContent>
        <TabsContent value="availability"><AvailabilityTab /></TabsContent>
        <TabsContent value="time"><TimeTab /></TabsContent>
        <TabsContent value="map"><MapTab /></TabsContent>
        <TabsContent value="report"><ReportTab /></TabsContent>
      </Tabs>
    </div>
  );
}
