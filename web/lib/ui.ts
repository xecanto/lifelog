/**
 * Legacy style constants, now delegating to the design system.
 *
 * These predate `components/ui.tsx` and are still imported across the app.
 * Pointing them at the same tokens means every page picks up the new look
 * without a rewrite; new code should reach for the components instead.
 */

import { buttonClass, inputClass } from "@/components/ui";

export const primaryBtn = `mt-3 ${buttonClass("primary")}`;
export const secondaryBtn = buttonClass("secondary");
export const textInput = inputClass;
export const hint = "mb-2.5 text-sm text-muted";
