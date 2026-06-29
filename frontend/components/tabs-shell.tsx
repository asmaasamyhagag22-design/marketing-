"use client";

import { Activity, Clapperboard, FileText, ImageIcon, Quote, Target } from "lucide-react";

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
import { ReelStudioCard } from "./reel-studio-card";
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
      <TabsList className="h-auto flex-wrap gap-1">
        <TabsTrigger value="profile" className="gap-1.5">
          <FileText className="h-4 w-4" /> Profile
        </TabsTrigger>
        <TabsTrigger value="evidence" className="gap-1.5">
          <Quote className="h-4 w-4" /> Evidence
        </TabsTrigger>
        <TabsTrigger value="swot" className="gap-1.5">
          <Target className="h-4 w-4" /> SWOT
        </TabsTrigger>
        <TabsTrigger value="diagnostics" className="gap-1.5">
          <Activity className="h-4 w-4" /> Diagnostics
        </TabsTrigger>

        {enablePosterTab && (
          <TabsTrigger value="poster" className="gap-1.5">
            <ImageIcon className="h-4 w-4" /> Poster Studio
            <Badge className="ml-1 border-transparent bg-brand-gradient px-1.5 text-[10px] text-white">
              new
            </Badge>
          </TabsTrigger>
        )}

        {enablePosterTab && (
          <TabsTrigger value="reel" className="gap-1.5">
            <Clapperboard className="h-4 w-4" /> Reel Studio
            <Badge className="ml-1 border-transparent bg-brand-gradient px-1.5 text-[10px] text-white">
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

      {enablePosterTab && (
        <TabsContent value="reel" className="space-y-4">
          <ReelStudioCard profile={profile} />
        </TabsContent>
      )}
    </Tabs>
  );
}