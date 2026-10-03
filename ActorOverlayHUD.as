// ActorOverlayHUD.as
// School project demo: drawing a 2D overlay (boxes, names, distance) on top of
// 3D actors in your OWN Unreal Engine 4 project, using the Hazelight
// UnrealEngine-Angelscript plugin.
//
// Setup:
//   1. Put this file in your project's /Script folder.
//   2. In your GameMode, set HUD Class = AActorOverlayHUD.
//   3. Press Play. Every ACharacter in the level gets a bounding box + label.

class AActorOverlayHUD : AHUD
{
    UPROPERTY()
    FLinearColor BoxColor = FLinearColor(0.1f, 1.0f, 0.3f, 1.0f);

    UPROPERTY()
    FLinearColor TextColor = FLinearColor::White;

    UPROPERTY()
    float MaxDrawDistance = 5000.0f; // in Unreal units (cm)

    UFUNCTION(BlueprintOverride)
    void DrawHUD(int SizeX, int SizeY)
    {
        APlayerController PC = GetOwningPlayerController();
        if (PC == nullptr)
            return;

        APawn ViewPawn = PC.GetControlledPawn();

        TArray<ACharacter> Characters;
        GetAllActorsOfClass(Characters);

        for (ACharacter Char : Characters)
        {
            if (Char == ViewPawn)
                continue; // don't draw on ourselves

            float Distance = ViewPawn != nullptr
                ? Char.GetDistanceTo(ViewPawn)
                : 0.0f;
            if (Distance > MaxDrawDistance)
                continue;

            FVector2D Min, Max;
            if (!GetScreenBounds(PC, Char, Min, Max))
                continue;

            DrawBox(Min, Max);

            FString Label = f"{Char.GetName()}  ({Distance / 100.0f :.1} m)";
            DrawText(Label, TextColor, Min.X, Min.Y - 16.0f);
        }
    }

    // Projects the 8 corners of the actor's world bounding box to the screen
    // and returns the 2D rectangle that encloses them.
    bool GetScreenBounds(APlayerController PC, AActor Actor, FVector2D& OutMin, FVector2D& OutMax)
    {
        FVector Origin, Extent;
        Actor.GetActorBounds(true, Origin, Extent);

        OutMin = FVector2D(MAX_flt, MAX_flt);
        OutMax = FVector2D(-MAX_flt, -MAX_flt);

        for (int i = 0; i < 8; ++i)
        {
            FVector Corner = Origin + FVector(
                (i & 1) != 0 ? Extent.X : -Extent.X,
                (i & 2) != 0 ? Extent.Y : -Extent.Y,
                (i & 4) != 0 ? Extent.Z : -Extent.Z);

            FVector2D Screen;
            if (!PC.ProjectWorldLocationToScreen(Corner, Screen, false))
                return false; // a corner is behind the camera

            OutMin.X = Math::Min(OutMin.X, Screen.X);
            OutMin.Y = Math::Min(OutMin.Y, Screen.Y);
            OutMax.X = Math::Max(OutMax.X, Screen.X);
            OutMax.Y = Math::Max(OutMax.Y, Screen.Y);
        }
        return true;
    }

    void DrawBox(FVector2D Min, FVector2D Max)
    {
        const float T = 2.0f; // line thickness
        DrawLine(Min.X, Min.Y, Max.X, Min.Y, BoxColor, T); // top
        DrawLine(Min.X, Max.Y, Max.X, Max.Y, BoxColor, T); // bottom
        DrawLine(Min.X, Min.Y, Min.X, Max.Y, BoxColor, T); // left
        DrawLine(Max.X, Min.Y, Max.X, Max.Y, BoxColor, T); // right
    }
}
