"use client";

import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";

import { ProfileCard } from "./profile-card";
import { OfferingsList } from "./offerings-list";
import { VisualIdentityCard } from "./visual-identity-card";
import { ValuePropsAndTrust } from "./value-props-and-trust";
import { DiagnosticsPanel } from "./diagnostics-panel";
import { PosterStudioCard } from "./poster-studio-card";
import { SwotCard } from "./swot-card";

import type { BusinessProfile, StageEvent } from "@/lib/types";

interface TabsShellProps {
  profile: BusinessProfile;
  events: StageEvent[];
  enablePosterTab: boolean;
}

export function TabsShell({ profile, events, enablePosterTab }: TabsShellProps) {
  return (
    <Tabs defaultValue="profile" className="w-full">
      <TabsList className="h-auto flex-wrap">
        <TabsTrigger value="profile">Profile</TabsTrigger>
        <TabsTrigger value="evidence">Evidence</TabsTrigger>
        <TabsTrigger value="swot">SWOT</TabsTrigger>
        <TabsTrigger value="diagnostics">Diagnostics</TabsTrigger>

        {enablePosterTab && (
          <TabsTrigger value="poster">
            Poster Studio
            <Badge variant="outline" className="ml-2 text-[10px]">
              new
            </Badge>
          </TabsTrigger>
        )}
      </TabsList>

      <TabsContent value="profile" className="space-y-4">
        <ProfileCard profile={profile} />
        <OfferingsList offerings={profile.offerings} />
        <VisualIdentityCard
          visual={profile.visual}
          contact={profile.contact_channels}
          socials={profile.social_presence}
          languages={profile.languages}
        />
      </TabsContent>

      <TabsContent value="evidence">
        <ValuePropsAndTrust
          valuePropositions={profile.value_propositions}
          trustSignals={profile.trust_signals}
          audienceSignals={profile.audience_signals}
          serviceAreas={profile.service_areas}
          existingCtas={profile.existing_ctas}
        />
      </TabsContent>

      <TabsContent value="swot" className="space-y-4">
        <SwotCard profile={profile} />
      </TabsContent>

      <TabsContent value="diagnostics">
        <DiagnosticsPanel profile={profile} events={events} />
      </TabsContent>

      {enablePosterTab && (
        <TabsContent value="poster" className="space-y-4">
          <PosterStudioCard profile={profile} />
        </TabsContent>
      )}
    </Tabs>
  );
}