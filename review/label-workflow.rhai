let meta = #{
    name: "jev-blind-label",
    description: "Blind-label 43 batches of Jev cards against the rubric",
    phases: [ #{ title: "Label", detail: "43 blinded batches" } ],
};

fn batch_name(i) {
    if i < 10 {
        "batch-0" + i.to_string()
    } else {
        "batch-" + i.to_string()
    }
}

phase("Label");
let jobs = [];
for i in 0..43 {
    let name = batch_name(i);
    let prompt = "You are an independent labeller. Work only from the card text. ";
    prompt += "Step 1: read this file completely with read_file and follow every rule in it: ";
    prompt += "/Users/matthew.oriordan/Workshop/work/projects/jev-landscape/review/work/LABEL.md. ";
    prompt += "Step 2: read only this JSONL file, every line: ";
    prompt += "/Users/matthew.oriordan/Workshop/work/projects/jev-landscape/review/blind/" + name + ".jsonl. ";
    prompt += "Step 3: write one JSON object per input card, same ids, same order, to ";
    prompt += "/Users/matthew.oriordan/Workshop/work/projects/jev-landscape/review/labels/" + name + ".jsonl. ";
    prompt += "Create that file with the write tool. Overwrite if it exists. ";
    prompt += "Do not read any other file. Do not open data/, report/, strata.json, any classified file, or any hand-labels file. ";
    prompt += "Do not create a git worktree. Do not run git. Do not modify the blind file or LABEL.md. ";
    prompt += "Read each card's t and x before you label it. If a field is not stated, use the empty value (unclear, none, false). ";
    prompt += "A digit in x that is the author's own count, cost, latency or accuracy is measured_demo, unless it is a TypeSafe launch figure or not a measurement under LABEL.md. ";
    prompt += "When the file is written, reply with the line count only.";
    jobs.push(#{
        prompt: prompt,
        label: name,
        capability_mode: "read-write",
    });
}
let results = parallel(jobs);
let ok = 0;
let failed = 0;
for r in results {
    if r != () && r.success {
        ok += 1;
    } else {
        failed += 1;
    }
}
log(ok.to_string() + " label batches succeeded, " + failed.to_string() + " failed");
complete(#{ ok: ok, failed: failed });
