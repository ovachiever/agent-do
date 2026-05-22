const jl = db.getSiblingDB("justice_league");

jl.heroes.updateOne(
  { name: "Green Lantern" },
  { $set: { alterEgo: "Kyle Rayner" } },
);
