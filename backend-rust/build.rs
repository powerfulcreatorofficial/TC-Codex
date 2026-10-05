use std::path::Path;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let proto_dir = Path::new("proto");
    tonic_build::configure()
        .build_server(true)
        .build_client(true)
        .compile_protos(
            &[
                proto_dir.join("daemon.proto"),
                proto_dir.join("health.proto"),
            ],
            &[proto_dir],
        )?;
    println!("cargo:rerun-if-changed=proto/daemon.proto");
    println!("cargo:rerun-if-changed=proto/health.proto");
    Ok(())
}
